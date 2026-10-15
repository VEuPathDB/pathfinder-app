---
type: Decision
title: The logo is a tsetse in a loop of the site colours
description: The PathFinder mark is a tsetse fly whose proboscis rests on the orange point where a search starts, search waves spreading from it, inside a three-part loop (frame, build, verify) coloured through the fourteen VEuPathDB site colours and notched once per site. A mosquito, a Toxoplasma rosette, the portal's navy, orange and rust, and site-coloured nodes were rejected because each reads as an existing VEuPathDB mark. One file set in assets/brand is the source; the web app names its copies in one module.
tags: [frontend, brand]
generated: { by: claude-code/opus-5.5, at: 2026-10-15T00:00:00Z }
status: stable
---

# What was decided

**The mark is the logo, with no name.** A tsetse fly in side profile, drawn with the
traits that identify Glossina: wings folded like closed scissors past the abdomen,
the hatchet cell in the wing veins, and a fine proboscis with a bulb at its base.
The proboscis tip rests on an orange point, and search waves spread from it. A
lockup with the name beside it exists for places that must spell the name out.

**The loop is the agent.** Three tapered segments, one each for frame, build and
verify, each growing from thin to thick into the next. The loop turns while the
agent works.

**The loop carries the consortium.** Its colour runs through the fourteen site
colours, each sampled from that site's icon in `apps/web/public/icons/`, and a notch
marks each site. On dark surfaces the dark end of the loop is lifted toward white,
so no part of the ring disappears into the background.

**One source.** `assets/brand/` holds every file and the rules. The web app serves
copies from `apps/web/public/brand/` and names them only in
`apps/web/src/lib/brand.ts`; `PathFinderLogo` is the one component that draws the
mark, and it switches the light and dark files with the app theme.
`brand.test.ts` fails when a served copy differs from the kit. The API
documentation reads the marks and the favicon from the kit.

# What was rejected

- **A mosquito.** The VEuPathDB emblem is a mosquito in a broken ring. A
  mosquito with search waves read as a variant of that emblem, not a product of
  its own.
- **A Toxoplasma rosette.** It names one organism of fourteen, and a disc with a
  rosette sits close to the ToxoDB icon.
- **The portal's navy, orange and rust.** The mark read as the portal's own.
- **Fourteen site-coloured nodes on a ring.** The mark read as OrthoMCL's.
- **Accent per site.** A navy mark taking the host site's colour would need a
  colour per deployment; one mark everywhere was preferred.
- **Illustrated, glossy organisms.** At icon sizes they read as cartoons, and the
  mark has to hold at 16 px.
