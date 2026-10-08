export const BASE_PATH = "/pathfinder";

export function withBasePath(path: string): string {
  return path.startsWith(`${BASE_PATH}/`) ? path : `${BASE_PATH}${path}`;
}
