MagLab PowerPoint stub template
================================

Template stub: this directory holds the PowerPoint (.pptx) template stub.
Format:        python-pptx
Loaded by:     SlidesDrafter (fmt="pptx")

A real .pptx template file requires binary PowerPoint authoring.
The SlidesDrafter generates slides programmatically via python-pptx,
starting from a widescreen 16:9 page (13.333 in x 7.5 in). This matches
Microsoft PowerPoint's Widescreen preset.

To use a custom institutional .pptx theme:
  1. Place your institutional theme file as "template.pptx" in this directory.
  2. The Word/PPTX export path in SlidesDrafter._export_pptx will prefer
     this template over the blank default when it exists.

If this directory is empty, SlidesDrafter generates slides from the
python-pptx default layout after setting slide_width and slide_height to
the widescreen 16:9 preset.
