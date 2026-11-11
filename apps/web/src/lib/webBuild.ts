export function currentWebBuild(): string {
  return process.env.PATHFINDER_WEB_BUILD ?? "";
}

export function aNewerBuildIsServed({
  mine,
  served,
}: {
  mine: string;
  served: string;
}): boolean {
  return mine !== "" && served !== "" && served !== mine;
}
