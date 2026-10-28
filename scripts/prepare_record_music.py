"""Prepare attributed, full-length Opus scores; run only when refreshing assets."""
from __future__ import annotations
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import subprocess
import httpx
from bs4 import BeautifulSoup

TRACKS = ['hiraeth','solace','with-these-hands','echoes-of-home','wildflowers',
          'memories-of-stone','home-was-you','aurora','born-of-the-sky','aphelion',
          'convergence','cirrus','in-this-moment','origami','hyperion']

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--ffmpeg',required=True)
    parser.add_argument('--cache',type=Path,required=True);parser.add_argument('--only',type=int,nargs='*');args=parser.parse_args()
    dest=Path(__file__).resolve().parents[1]/'paperscientist/static/intro/audio/records'
    dest.mkdir(parents=True,exist_ok=True);args.cache.mkdir(parents=True,exist_ok=True)
    def prepare(pair):
        mask,slug=pair;page=f'https://www.scottbuckley.com.au/library/{slug}/'
        with httpx.Client(follow_redirects=True,timeout=90) as client:
            response=client.get(page);response.raise_for_status();html=response.text
            soup=BeautifulSoup(html,'html.parser');title=soup.select_one('h1').get_text(strip=True)
            links=[a['href'] for a in soup.select('a[href]') if '.mp3' in a['href'].lower() and 'scottbuckley.com.au' in a['href']]
            assert links and 'creativecommons.org/licenses/by/4.0' in html,slug
            download=links[0];source=args.cache/f'{slug}.mp3'
            if not source.exists():
                r=client.get(download);r.raise_for_status();source.write_bytes(r.content)
        output=dest/(f'{mask:02}-hyperion.opus' if mask==15 else f'{mask:02}.opus')
        if not output.exists():
            subprocess.run([args.ffmpeg,'-hide_banner','-loglevel','error','-y','-i',str(source),
                '-vn','-map_metadata','-1','-c:a','libopus','-b:a','80k','-vbr','on',
                '-metadata',f'title={title}','-metadata','artist=Scott Buckley',
                '-metadata','copyright=CC BY 4.0; www.scottbuckley.com.au',str(output)],check=True)
        print(f'{mask:02} {title}: {output.stat().st_size} bytes',flush=True)
        return dict(mask=mask,title=title,author='Scott Buckley',page=page,download=download,
                    license='CC BY 4.0',license_url='https://creativecommons.org/licenses/by/4.0/',
                    changes='Full-length Opus transcode at 80 kbps VBR; no cuts. Playback gain and crossfade only.',
                    sha256=hashlib.sha256(output.read_bytes()).hexdigest(),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),bytes=output.stat().st_size)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        pairs=[p for p in enumerate(TRACKS,1) if not args.only or p[0] in args.only]
        rows=list(pool.map(prepare,pairs))
    if args.only:
        previous=json.loads((dest/'credits.json').read_text(encoding='utf-8'))
        updated={r['mask']:r for r in previous};updated.update({r['mask']:r for r in rows});rows=sorted(updated.values(),key=lambda r:r['mask'])
    (dest/'credits.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

if __name__=='__main__':main()
