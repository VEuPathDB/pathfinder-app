import { createContext } from "react";

export interface FigureSection {
  letter: string;
  title: string;
}

export const FigureSectionContext = createContext<FigureSection | null>(null);
