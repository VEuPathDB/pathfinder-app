"use client";

import Image from "next/image";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useInterval, useTimeout } from "usehooks-ts";

const COUNTDOWN_SECONDS = 3;

export default function NotFound() {
  const router = useRouter();
  const [count, setCount] = useState(COUNTDOWN_SECONDS);

  useInterval(() => {
    setCount((c) => (c > 0 ? c - 1 : 0));
  }, 1000);

  useTimeout(() => {
    router.replace("/");
  }, COUNTDOWN_SECONDS * 1000);

  return (
    <div className="flex h-full min-h-screen flex-col items-center justify-center bg-background px-6 text-center text-foreground">
      <Image src="/pathfinder.svg" alt="PathFinder" width={64} height={64} priority />
      <h1 className="mt-6 text-2xl font-semibold tracking-tight sm:text-3xl">
        PathFinder
      </h1>
      <p className="mt-6 text-xl font-medium text-foreground">
        Whoops - this page couldn&apos;t be found.
      </p>
      <p className="mt-2 text-sm text-muted-foreground" aria-live="polite">
        Redirecting home in {count}...
      </p>
    </div>
  );
}
