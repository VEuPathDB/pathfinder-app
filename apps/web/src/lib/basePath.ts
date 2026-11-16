export const BASE_PATH = "/strategist";

export function withBasePath(path: string): string {
  return path.startsWith(`${BASE_PATH}/`) ? path : `${BASE_PATH}${path}`;
}
