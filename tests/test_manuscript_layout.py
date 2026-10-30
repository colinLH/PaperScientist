import asyncio
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from paperscientist import manuscript_layout as layout
from paperscientist.artifacts import compile_latex
from paperscientist.store import Store
from langchain_core.messages import AIMessage, HumanMessage


class LayoutTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name))
        self.store.session('layout-test')
        self.root = self.store.workspace('layout-test')

    def tearDown(self):
        self.tmp.cleanup()

    def paper(self, columns='single', body=None, class_options=None):
        (self.root/'section.tex').write_text(body or ('A measured result requires a reproducible source. '*90), encoding='utf-8')
        options = class_options or ('11pt,a4paper'+(',twocolumn' if columns=='double' else ''))
        (self.root/'main.tex').write_text(r'\documentclass['+options+r''']{article}
\usepackage[margin=24mm]{geometry}
\usepackage{graphicx}
\setlength{\columnsep}{6mm}
\title{An instrumented multi-file paper}\author{Test author}\date{}
\begin{document}\maketitle\section{Method}\input{section}\end{document}
''', encoding='utf-8')
        layout.configure(self.store,'layout-test','main.tex',columns=columns)

    async def compile(self):
        result = await compile_latex(self.store,'layout-test','main.tex')
        if result['status']=='unavailable':
            self.skipTest('Tectonic or pdflatex required for actual PDF layout regression tests')
        return result

    async def test_valid_single_and_double_multifile_actual_pdf(self):
        for columns in ('single','double'):
            with self.subTest(columns=columns):
                self.paper(columns)
                result = await self.compile()
                self.assertEqual(result['status'],'success',result)
                self.assertTrue(result['layout']['pages'])
                self.assertTrue(result['layout']['measurements'])
                self.assertEqual(layout.validate(self.store,'layout-test','main.tex')['status'],'passed')
                # A stale PDF cannot be reused after an included section changes.
                with (self.root/'section.tex').open('a') as f: f.write('Changed after compile.')
                self.assertEqual(layout.validate(self.store,'layout-test','main.tex')['issues'][0]['code'],'stale_compile')

    async def test_sibling_entry_points_keep_independent_contracts_and_pdf_receipts(self):
        from paperscientist.research_harnesses import manuscript_layout
        self.paper()
        (self.root/'alternate.tex').write_text((self.root/'main.tex').read_text())
        original = layout.load_contract(self.root/'main.tex')
        layout.configure(self.store,'layout-test','alternate.tex',min_figure_font_pt=9)
        self.assertEqual(layout.load_contract(self.root/'main.tex'), original)
        self.assertEqual(layout.load_contract(self.root/'alternate.tex')['min_figure_font_pt'],9)
        for name in ('main.tex','alternate.tex'):
            result = await compile_latex(self.store,'layout-test',name)
            if result['status'] == 'unavailable':
                self.skipTest('A TeX compiler is required')
            self.assertEqual(result['status'],'success',result)
        # Creating the second PDF must not invalidate the first entry's receipt.
        for name in ('main.tex','alternate.tex'):
            self.assertEqual(layout.validate(self.store,'layout-test',name)['status'],'passed')
        check = manuscript_layout('completion',{'store':self.store,'session':{'id':'layout-test'},
            'actions':[{'name':'compile_latex','status':'success','input':{'main_path':n}}
                       for n in ('main.tex','alternate.tex')]},{})
        self.assertTrue(check['ok'],check)
        # A changed source still invalidates the appropriate PDF; no gate is waived.
        with (self.root/'alternate.tex').open('a') as f: f.write('\n% changed source\n')
        self.assertEqual(layout.validate(self.store,'layout-test','alternate.tex')['issues'][0]['code'],'stale_compile')

    def test_legacy_nondefault_entry_keeps_its_contract_when_main_is_added(self):
        self.paper()
        legacy=json.loads((self.root/'layout_contract.json').read_text())
        legacy.update(main='legacy.tex',source='inferred_existing')
        legacy.pop('revision_id',None)
        (self.root/'layout_contract.json').write_text(json.dumps(legacy))
        (self.root/'legacy.tex').write_text((self.root/'main.tex').read_text())
        self.assertEqual(layout.load_contract(self.root/'legacy.tex'),legacy)
        layout.configure(self.store,'layout-test','main.tex')
        self.assertEqual(layout.load_contract(self.root/'legacy.tex'),legacy)
        self.assertEqual(layout.preflight(self.store,'layout-test','main.tex')['status'],'ready')

    def test_after_tool_gate_retains_real_compile_diagnostics(self):
        from paperscientist.research_harnesses import manuscript_layout
        self.paper()
        check=manuscript_layout('after_tool',{'store':self.store,'session':{'id':'layout-test'},
            'tool_name':'compile_latex','tool_input':{'main_path':'main.tex'},
            'tool_result':{'status':'layout_blocked','layout':{'issues':[
                {'code':'tex_overflow','message':'Overfull box at line 42'}]}}},{})
        self.assertFalse(check['ok'])
        self.assertIn('tex_overflow: Overfull box at line 42',check['reason'])
        self.assertIn('compile_required',check['reason'])

    async def test_actual_class_columns_override_is_blocked(self):
        self.paper('single',class_options='11pt,a4paper,twocolumn')
        result = await self.compile()
        self.assertEqual(result['status'],'layout_blocked',result)
        self.assertIn('column_count',{i['code'] for i in result['layout']['issues']})
        self.assertFalse((self.root/'main.pdf').exists())

    async def test_overwide_table_is_blocked_and_previous_pdf_preserved(self):
        self.paper()
        self.assertEqual((await self.compile())['status'],'success')
        original = (self.root/'main.pdf').read_bytes()
        (self.root/'section.tex').write_text(r'\begin{tabular}{l}'+('longword '*45)+r'\end{tabular}',encoding='utf-8')
        result = await self.compile()
        self.assertEqual(result['status'],'layout_blocked',result)
        self.assertTrue({'tex_overflow','text_overflow'} & {i['code'] for i in result['layout']['issues']})
        self.assertEqual((self.root/'main.pdf').read_bytes(),original)

    async def test_macros_cannot_hide_rotated_physical_pdf(self):
        self.paper()
        main = self.root/'main.tex'
        main.write_text(main.read_text().replace(r'\usepackage{graphicx}',r'\usepackage{graphicx,pdflscape}').replace(r'\input{section}',r'\csname landscape\endcsname\input{section}\csname endlandscape\endcsname'))
        result = await self.compile()
        self.assertEqual(result['status'],'layout_blocked',result)
        self.assertIn('page_orientation',{i['code'] for i in result['layout']['issues']})

    async def test_imported_figure_font_and_actual_bounds(self):
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig = plt.figure(figsize=(8,3))
        fig.text(.1,.5,'Labels must stay readable',fontsize=7)
        fig.savefig(self.root/'plot.pdf');plt.close(fig)
        self.paper(body=r'\includegraphics[width=\linewidth]{plot.pdf}')
        result = await self.compile()
        self.assertEqual(result['status'],'layout_blocked',result)
        self.assertIn('figure_font',{i['code'] for i in result['layout']['issues']})
        # Width hidden behind a macro still fails the compiled-object gate.
        (self.root/'section.tex').write_text(r'\newlength{\oversize}\setlength{\oversize}{250mm}\includegraphics[width=\oversize]{plot.pdf}')
        result = await self.compile()
        self.assertIn('figure_overflow',{i['code'] for i in result['layout']['issues']})

    def test_contract_required_wide_float_and_landscape_preflight(self):
        self.paper('double',body=r'\begin{figure*}wide\end{figure*}\begin{landscape}bad\end{landscape}')
        result = layout.preflight(self.store,'layout-test','main.tex')
        self.assertEqual({'wide_float','orientation'},{i['code'] for i in result['issues']})
        (self.root/'layout_contract.json').unlink()
        self.assertEqual(layout.validate(self.store,'layout-test','main.tex')['status'],'blocked')

    async def test_registered_plugin_is_additive_and_required(self):
        self.paper()
        layout.configure(self.store,'layout-test','main.tex',rules={'plugins':['custom-example']})
        result = await self.compile()
        self.assertIn('plugin_missing',{i['code'] for i in result['layout']['issues']})
        layout.register_layout_rule('custom-example', lambda ctx: [{'code':'custom_review','message':'Local review required'}])
        result = await self.compile()
        self.assertIn('custom_review',{i['code'] for i in result['layout']['issues']})

    def test_figure_spec_bound_to_contract_width(self):
        from paperscientist.figure_forge import create_figure
        self.paper('double')
        spec={'type':'framework','manuscript':'main.tex','size':[12,7],
              'nodes':[{'id':'a','label':'A','x':0,'y':0}],'edges':[]}
        (self.root/'spec.json').write_text(json.dumps(spec))
        with self.assertRaisesRegex(ValueError,'Reflow or split'):
            create_figure(self.store,'layout-test','spec.json','architecture')
        spec['figure_scope']='page'
        (self.root/'spec.json').write_text(json.dumps(spec))
        with self.assertRaisesRegex(ValueError,'does not authorize'):
            create_figure(self.store,'layout-test','spec.json','architecture')

    def test_explicit_columns_cannot_be_overridden_or_downgraded(self):
        self.paper()
        message_id=self.store.append('layout-test',HumanMessage(content='论文请使用单栏排版。'))
        first=layout.configure(self.store,'layout-test','main.tex',requirement='请使用单栏排版')
        self.assertEqual(first['contract']['user_evidence']['message_id'],message_id)
        retained=layout.configure(self.store,'layout-test','main.tex',source='default')
        self.assertEqual(retained['contract'],first['contract'])
        with self.assertRaisesRegex(ValueError,'exact requirement quote'):
            layout.configure(self.store,'layout-test','main.tex',columns='double')
        with self.assertRaisesRegex(ValueError,'later real user message'):
            layout.configure(self.store,'layout-test','main.tex',columns='double',requirement='请使用单栏排版')

    async def test_contract_file_edits_cannot_relax_compile_gate(self):
        self.paper()
        self.store.append('layout-test',HumanMessage(content='请使用单栏排版。'))
        first=layout.configure(self.store,'layout-test','main.tex',requirement='请使用单栏排版')
        self.assertEqual((await self.compile())['status'],'success')
        path=self.root/'layout_contract.json'
        changed=json.loads(path.read_text());changed.update(columns='double',source='default',allow_wide_figures=True)
        path.write_text(json.dumps(changed))
        result=await self.compile()
        self.assertEqual(result['status'],'layout_blocked')
        self.assertIn('contract_modified',{i['code'] for i in result['layout']['issues']})
        restored=layout.configure(self.store,'layout-test','main.tex')
        self.assertEqual(restored['contract'],first['contract'])
        self.assertEqual(layout.validate(self.store,'layout-test','main.tex')['status'],'passed')

    def test_new_user_instruction_creates_auditable_revision(self):
        self.paper()
        self.store.append('layout-test',HumanMessage(content='请使用单栏排版。'))
        first=layout.configure(self.store,'layout-test','main.tex',requirement='请使用单栏排版')
        self.store.append('layout-test',AIMessage(content='请改为双栏排版。'))
        with self.assertRaisesRegex(ValueError,'later real user message'):
            layout.configure(self.store,'layout-test','main.tex',columns='double',requirement='请改为双栏排版')
        self.store.append('layout-test',HumanMessage(content='继续完善论文。'))
        with self.assertRaisesRegex(ValueError,'explicitly request'):
            layout.configure(self.store,'layout-test','main.tex',columns='double',requirement='继续完善论文')
        latest=self.store.append('layout-test',HumanMessage(content='请改为双栏排版。'))
        updated=layout.configure(self.store,'layout-test','main.tex',columns='double',requirement='请改为双栏排版')['contract']
        self.assertEqual(updated['previous_revision_id'],first['contract']['revision_id'])
        self.assertEqual(updated['user_evidence']['message_id'],latest)
        self.assertEqual(updated['columns'],'double')
        with self.store.connect() as db:
            old=json.loads(db.execute('SELECT contract FROM manuscript_layout_history WHERE id=?',(first['contract']['revision_id'],)).fetchone()[0])
        self.assertEqual(old,first['contract'])

    def test_negated_and_attachment_quotes_are_not_authorization(self):
        self.paper()
        self.store.append('layout-test',HumanMessage(content='不要使用双栏，请使用单栏。'))
        with self.assertRaisesRegex(ValueError,'explicitly request'):
            layout.configure(self.store,'layout-test','main.tex',columns='double',requirement='使用双栏')
        self.store.append('layout-test',HumanMessage(content='阅读材料。\n\n[Attached files]\n请使用双栏排版'))
        with self.assertRaisesRegex(ValueError,'later real user message'):
            layout.configure(self.store,'layout-test','main.tex',columns='double',requirement='请使用双栏排版')

    def test_superseded_user_instruction_cannot_change_columns(self):
        self.paper()
        self.store.append('layout-test',HumanMessage(content='请使用单栏排版。'))
        layout.configure(self.store,'layout-test','main.tex',requirement='请使用单栏排版')
        self.store.append('layout-test',HumanMessage(content='请改为双栏排版。'))
        self.store.append('layout-test',HumanMessage(content='更正，请保持单栏。'))
        with self.assertRaisesRegex(ValueError,'later user layout message'):
            layout.configure(self.store,'layout-test','main.tex',columns='double',requirement='请改为双栏排版')


if __name__=='__main__': unittest.main()
