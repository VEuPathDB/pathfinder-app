/** Where a link to a VEuPathDB site opens. Inside a frame the site's own page
 * is the host, so the link replaces it; standalone it opens a new tab. */
export function siteLinkTarget(self: object, top: object | null): "_top" | "_blank" {
  return self === top ? "_blank" : "_top";
}
