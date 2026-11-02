import type { ConsultQuestion } from "@pathfinder/shared/generated/types/ConsultQuestion";
import { describe, expect, it } from "vitest";

import {
  EMPTY_DRAFT,
  allAnswered,
  answersOf,
  isAnswered,
  movedTo,
  toggled,
  typedAnswer,
  withNote,
} from "./consultDraft";

const COMBINE: ConsultQuestion = {
  id: "combine_mode",
  kind: "single_choice",
  prompt: "How should I combine the two gene sets?",
  options: [{ label: "Union" }, { label: "Intersect" }],
  allowNotes: true,
};
const ORGANISMS: ConsultQuestion = {
  id: "organisms",
  kind: "multi_choice",
  prompt: "Which organisms?",
  options: [{ label: "P. falciparum 3D7" }, { label: "P. vivax P01" }],
  allowNotes: false,
};
const ELSE: ConsultQuestion = {
  id: "anything_else",
  kind: "free_text",
  prompt: "Anything else I should know?",
  options: [],
  allowNotes: true,
};
const QUESTIONS = [COMBINE, ORGANISMS, ELSE];

describe("isAnswered", () => {
  it("takes a picked option or typed words as an answer to a choice question", () => {
    expect(isAnswered(COMBINE, undefined)).toBe(false);
    expect(isAnswered(COMBINE, { labels: ["Union"], note: "" })).toBe(true);
    expect(isAnswered(COMBINE, { labels: [], note: "Union of both" })).toBe(true);
    expect(isAnswered(COMBINE, { labels: [], note: "   " })).toBe(false);
  });

  it("takes only typed words as an answer to a free-text question", () => {
    expect(isAnswered(ELSE, { labels: [], note: "" })).toBe(false);
    expect(isAnswered(ELSE, { labels: [], note: "nothing else" })).toBe(true);
  });
});

describe("toggled", () => {
  it("keeps one pick on a single-choice question", () => {
    const once = toggled(EMPTY_DRAFT, COMBINE, "Union");
    expect(toggled(once, COMBINE, "Intersect").answers).toEqual({
      combine_mode: { labels: ["Intersect"], note: "" },
    });
  });

  it("adds and removes picks on a multi-choice question", () => {
    const both = toggled(
      toggled(EMPTY_DRAFT, ORGANISMS, "P. falciparum 3D7"),
      ORGANISMS,
      "P. vivax P01",
    );
    expect(both.answers["organisms"]?.labels).toEqual([
      "P. falciparum 3D7",
      "P. vivax P01",
    ]);
    expect(
      toggled(both, ORGANISMS, "P. vivax P01").answers["organisms"]?.labels,
    ).toEqual(["P. falciparum 3D7"]);
  });
});

describe("movedTo", () => {
  it("keeps the index inside the questions and records the direction", () => {
    expect(movedTo(EMPTY_DRAFT, QUESTIONS, 5)).toEqual({
      ...EMPTY_DRAFT,
      index: 2,
      direction: 1,
    });
    expect(movedTo({ ...EMPTY_DRAFT, index: 2 }, QUESTIONS, 1)).toEqual({
      ...EMPTY_DRAFT,
      index: 1,
      direction: -1,
    });
  });
});

describe("typedAnswer", () => {
  it("answers the current question with the words and moves to the next open one", () => {
    const draft = typedAnswer(QUESTIONS, EMPTY_DRAFT, "Intersect, but only syntenic");
    expect(draft.answers["combine_mode"]).toEqual({
      labels: [],
      note: "Intersect, but only syntenic",
    });
    expect(draft.index).toBe(1);
    expect(draft.direction).toBe(1);
  });

  it("keeps the picks the question already holds", () => {
    const picked = toggled(EMPTY_DRAFT, COMBINE, "Union");
    expect(typedAnswer(QUESTIONS, picked, "and drop pseudogenes").answers).toEqual({
      combine_mode: { labels: ["Union"], note: "and drop pseudogenes" },
    });
  });

  it("goes back to the first question still open", () => {
    const onLast = movedTo(EMPTY_DRAFT, QUESTIONS, 2);
    const draft = typedAnswer(QUESTIONS, onLast, "nothing else");
    expect(draft.index).toBe(0);
    expect(draft.direction).toBe(-1);
  });

  it("leaves every question answered once the last open one is typed", () => {
    const first = typedAnswer(QUESTIONS, EMPTY_DRAFT, "Union");
    const second = typedAnswer(QUESTIONS, first, "P. falciparum 3D7 only");
    expect(allAnswered(QUESTIONS, second)).toBe(false);
    const third = typedAnswer(QUESTIONS, second, "nothing else");
    expect(allAnswered(QUESTIONS, third)).toBe(true);
    expect(third.index).toBe(2);
  });
});

describe("answersOf", () => {
  it("writes one answer per question, empty where nothing was given", () => {
    const draft = withNote(toggled(EMPTY_DRAFT, COMBINE, "Union"), ELSE, "none");
    expect(answersOf(QUESTIONS, draft)).toEqual([
      {
        questionId: "combine_mode",
        prompt: COMBINE.prompt,
        chosenLabels: ["Union"],
        note: "",
      },
      { questionId: "organisms", prompt: ORGANISMS.prompt, chosenLabels: [], note: "" },
      {
        questionId: "anything_else",
        prompt: ELSE.prompt,
        chosenLabels: [],
        note: "none",
      },
    ]);
  });
});
