// Album print template. It only draws: every position, size and crop was decided in Python
// (domain/print_layout.py) and arrives in `sys.inputs.job` as JSON, lengths in millimetres,
// page coordinates with the origin at the top-left corner of the trim.

#let job = json(bytes(sys.inputs.job))
#let t = job.theme
#let mm(v) = v * 1mm
#let origin = job.sheet.origin

#set document(title: job.title)
#set text(font: t.font, fill: rgb(t.ink), size: t.text_size * 1pt, lang: "en", hyphenate: false)
#set par(leading: 0.72em, spacing: 1.1em, justify: false)

#let crop-mark(m) = place(line(
  start: (mm(m.at(0)), mm(m.at(1))),
  end: (mm(m.at(2)), mm(m.at(3))),
  stroke: 0.25pt + black,
))

#set page(
  width: mm(job.sheet.width),
  height: mm(job.sheet.height),
  margin: 0pt,
  background: {
    let s = job.sheet.paper
    place(dx: mm(s.x), dy: mm(s.y), rect(width: mm(s.w), height: mm(s.h), fill: rgb(t.paper), stroke: none))
    for m in job.sheet.marks { crop-mark(m) }
  },
)

// A photo: a clipping frame; inside it the whole image, scaled and shifted so that exactly
// the crop rectangle fills the frame. Typst embeds the original pixels, so print resolution
// is untouched.
#let photo(f) = place(dx: mm(origin + f.x), dy: mm(origin + f.y), box(
  width: mm(f.w),
  height: mm(f.h),
  clip: true,
  place(dx: mm(f.dx), dy: mm(f.dy), image(f.path, width: mm(f.img_w), height: mm(f.img_h), fit: "stretch")),
))

// Text whose first baseline sits exactly at y: one baseline for every caption in the album.
// Lines have zero height (both edges on the baseline), so `leading` is the baseline-to-baseline
// distance: text sits on a regular grid.
#let on-baseline(x, y, w, body) = place(dx: mm(origin + x), dy: mm(origin + y), box(width: mm(w), {
  set text(top-edge: "baseline", bottom-edge: "baseline")
  set par(leading: 1.42em, spacing: 2.3em)
  body
}))

#let caption(c) = on-baseline(c.x, c.y, c.w, text(size: t.caption_size * 1pt, fill: rgb(t.ink_secondary), c.text))

#let title(c) = on-baseline(c.x, c.y, c.w, {
  set par(spacing: t.title_size * 1pt)  // subtitle baseline one title-size below the title
  text(size: t.title_size * 1pt, c.text)
  if c.subtitle != "" {
    parbreak()
    text(size: t.text_size * 1.15pt, fill: rgb(t.ink_secondary), c.subtitle)
  }
})

#let prose(b) = on-baseline(b.x, b.y, b.w, {
  for para in b.text.split("\n\n") { par(para.trim()) }
})

#for (i, p) in job.pages.enumerate() {
  if i > 0 { pagebreak() }
  for f in p.frames { photo(f) }
  if p.caption != none { caption(p.caption) }
  if p.title != none { title(p.title) }
  if p.prose != none { prose(p.prose) }
  // An empty page still needs content to exist.
  box()
}
