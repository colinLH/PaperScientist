"""Conversation layout with the original aurora, glass, and particle theme."""
from pathlib import Path
import gradio as gr

_STATIC = Path(__file__).parent / "static"
CSS = "\n".join((_STATIC / name).read_text(encoding="utf-8")
                for name in ("timeline.css", "effects.css"))
# Gradio scopes the component CSS and drops @property rules. Register the angle
# in the document head so the border interpolates continuously in every panel.
HEAD = ("<style>@property --ps-angle {syntax:'<angle>'; initial-value:0deg; inherits:false;}</style>"
        "<script>" + (_STATIC / "effects.js").read_text(encoding="utf-8") + "</script>")

def theme():
    return gr.themes.Base(primary_hue="violet", neutral_hue="gray", font=["Segoe UI", "Microsoft YaHei", "sans-serif"]).set(
        body_background_fill="transparent", body_background_fill_dark="transparent",
        body_text_color="#e7e5f2", body_text_color_dark="#e7e5f2",
        background_fill_primary="#15151f", background_fill_primary_dark="#15151f",
        background_fill_secondary="#1c1c2a", background_fill_secondary_dark="#1c1c2a",
        block_background_fill="rgba(18,18,30,.62)", block_background_fill_dark="rgba(18,18,30,.62)",
        block_border_color="rgba(255,255,255,.08)", block_border_color_dark="rgba(255,255,255,.08)",
        block_shadow="0 10px 30px rgba(0,0,0,.30)", block_shadow_dark="0 10px 30px rgba(0,0,0,.30)",
        input_background_fill="rgba(255,255,255,.04)", input_background_fill_dark="rgba(255,255,255,.04)",
        input_border_color="rgba(255,255,255,.10)", input_border_color_dark="rgba(255,255,255,.10)",
        input_border_color_focus="rgba(124,92,255,.65)", input_border_color_focus_dark="rgba(124,92,255,.65)",
        button_secondary_background_fill="rgba(255,255,255,.06)", button_secondary_background_fill_dark="rgba(255,255,255,.06)",
        button_secondary_text_color="#dddddd", button_secondary_text_color_dark="#dddddd",
        button_secondary_background_fill_hover="rgba(124,92,255,.22)", button_secondary_background_fill_hover_dark="rgba(124,92,255,.22)",
        checkbox_background_color_selected="#7c5cff", checkbox_background_color_selected_dark="#7c5cff",
        color_accent="#7c5cff", color_accent_soft="rgba(124,92,255,.18)", color_accent_soft_dark="rgba(124,92,255,.18)",
        body_text_color_subdued="#a9a6bd", body_text_color_subdued_dark="#a9a6bd")
