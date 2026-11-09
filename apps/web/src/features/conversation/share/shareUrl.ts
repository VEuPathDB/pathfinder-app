import { withBasePath } from "@/lib/basePath";

export function shareUrl(
  token: string,
  pageUrl: string | null,
  origin: string,
): string {
  const path = `/shared/${token}`;
  return pageUrl === null ? `${origin}${withBasePath(path)}` : `${pageUrl}${path}`;
}
