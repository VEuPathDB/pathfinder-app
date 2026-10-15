# PathFinder brand

The PathFinder logo is a mark with no name: a tsetse fly whose proboscis rests on
the orange point where a search starts, search waves spreading from that point, and
a loop around both. The loop has three parts, one each for frame, build and verify,
and runs through the colours of the fourteen VEuPathDB sites. It turns while the
agent works.

Open `brand-guide.html` in a browser to see every file at its real size, on light
and dark, and in place.

## Files

| File | Use |
|---|---|
| `pathfinder-mark-light.svg` | The logo on white and light surfaces. |
| `pathfinder-mark-dark.svg` | The logo on navy and dark surfaces. |
| `pathfinder-mark-light-animated.svg` | The logo with the loop turning, for the agent's working state. |
| `pathfinder-mark-dark-animated.svg` | The animated logo for dark surfaces. |
| `favicon.svg` | The small-size cut, for 31 px and under. Follows the browser's light or dark setting. |
| `favicon-dark.svg` | The small-size cut in its dark colours only. |
| `favicon.ico` | 16, 32 and 48 px in one file. |
| `apple-touch-icon.png` | 180 px icon for iOS home screens. |
| `app-icon.svg` | The logo on a navy rounded square. |
| `app-icon-small.svg` | The app icon built from the small-size cut, for 48 px and under. |
| `social-card.svg` | 1200 by 630 link preview. |
| `pathfinder-lockup-light.svg` | Optional: the logo with the name beside it. |
| `pathfinder-lockup-dark.svg` | Optional: the same, for dark surfaces. |
| `png/` | PNG exports of the above. |

## Rules

- The logo is the mark alone. Use a lockup only where the name must be spelled out.
- Use the full mark at 32 px and up, and the small-size cut from 31 px to 16 px.
- Keep clear space of 15 percent of the mark's width on every side.
- Use the light mark on light surfaces and the dark mark on dark ones.

## Colour

| Role | Colour |
|---|---|
| Insect, waves | Navy `#00304c` |
| Search point | Orange `#e87722` |
| Loop | The fourteen site colours, each sampled from its site icon |

## Where the repository uses it

- The web app serves copies from `apps/web/public/brand/` and names them in
  `apps/web/src/lib/brand.ts`. A test fails if a copy differs from this folder, so a
  new logo is a change here, a copy there, and nothing else.
- The API documentation reads the marks and the favicon from this folder.
- The repository README shows the marks from this folder.
