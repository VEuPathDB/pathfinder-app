import { test, expect } from "../fixtures/a11y";
import { MOCK_PLAN_PROMPT } from "../fixtures/mock-prompts";

/**
 * The researcher journey, once per component site: site switch, multi-round
 * chat, a strategy from the planning artifact, and a follow-up turn. Real WDK,
 * real Postgres, real worker; only the LLM is mocked.
 */

interface ChatRound {
  readonly prompt: string;
  readonly reply: RegExp;
}

interface SiteJourney {
  readonly siteId: string;
  readonly title: string;
  readonly rounds: readonly ChatRound[];
  /** Query string of the conversations read that proves the strategy landed. */
  readonly conversationsQuery: string;
  readonly expectConversations: "ok" | "non-empty";
  readonly followUp?: ChatRound;
}

const JOURNEYS: readonly SiteJourney[] = [
  {
    siteId: "plasmodb",
    title: "malaria drug resistance",
    rounds: [
      {
        prompt:
          "I'm investigating chloroquine resistance mechanisms in Plasmodium falciparum",
        reply: /have not built anything yet/i,
      },
      {
        prompt: "Can you help me find genes involved in drug resistance?",
        reply: /\[mock\].*Can you help/,
      },
    ],
    conversationsQuery: "",
    expectConversations: "non-empty",
    followUp: {
      prompt: "Based on these results, what pathways should I investigate?",
      reply: /\[mock\].*pathways/i,
    },
  },
  {
    siteId: "toxodb",
    title: "toxoplasma host invasion",
    rounds: [
      {
        prompt: "I'm studying host cell invasion mechanisms in Toxoplasma gondii",
        reply: /\[mock\]/,
      },
      {
        prompt: "What micronemal and rhoptry proteins are involved in attachment?",
        reply: /\[mock\].*micronemal/i,
      },
    ],
    conversationsQuery: "?siteId=toxodb",
    expectConversations: "ok",
  },
  {
    siteId: "tritrypdb",
    title: "leishmania virulence factors",
    rounds: [
      {
        prompt: "I'm investigating virulence factors in Leishmania major",
        reply: /have not built anything yet/i,
      },
      {
        prompt: "What surface proteases are involved in host macrophage invasion?",
        reply: /\[mock\].*surface/i,
      },
    ],
    conversationsQuery: "",
    expectConversations: "non-empty",
    followUp: {
      prompt: "The strategy shows interesting protease genes, what about drug targets?",
      reply: /\[mock\].*drug targets/i,
    },
  },
  {
    siteId: "cryptodb",
    title: "cryptosporidium intestinal infection",
    rounds: [
      {
        prompt: "I'm studying Cryptosporidium parvum intestinal infection mechanisms",
        reply: /\[mock\]/,
      },
      {
        prompt: "What oocyst wall proteins are important for environmental survival?",
        reply: /\[mock\].*oocyst/i,
      },
    ],
    conversationsQuery: "?siteId=cryptodb",
    expectConversations: "ok",
  },
  {
    siteId: "fungidb",
    title: "fungal pathogenesis",
    rounds: [
      {
        prompt: "I'm researching antifungal drug targets in Aspergillus fumigatus",
        reply: /\[mock\]/,
      },
      {
        prompt: "What cell wall biosynthesis enzymes are potential drug targets?",
        reply: /\[mock\].*cell wall/i,
      },
      {
        prompt: "Particularly interested in glucan synthase and chitin synthase",
        reply: /\[mock\].*glucan/i,
      },
    ],
    conversationsQuery: "",
    expectConversations: "ok",
    followUp: {
      prompt:
        "The strategy confirms cell wall synthesis genes, what's the clinical relevance?",
      reply: /\[mock\].*clinical/i,
    },
  },
];

for (const journey of JOURNEYS) {
  test.describe(`${journey.title} journey on ${journey.siteId}`, () => {
    test("chat, strategy and API verification", async ({
      chatPage,
      graphPage,
      page,
      apiClient,
      sitePicker,
    }) => {
      await chatPage.goto();
      await sitePicker.selectSite(journey.siteId);
      await sitePicker.expectCurrentSite(journey.siteId);

      for (const round of journey.rounds) {
        await chatPage.send(round.prompt);
        await chatPage.expectAssistantMessage(round.reply);
        await chatPage.expectIdle();
      }

      await chatPage.send(MOCK_PLAN_PROMPT);
      await graphPage.expectRailPanel();
      await chatPage.expectIdle();

      const conversations = await apiClient.get(
        `/api/v1/conversations${journey.conversationsQuery}`,
      );
      expect(conversations.ok()).toBeTruthy();
      if (journey.expectConversations === "non-empty") {
        const rows = (await conversations.json()) as unknown[];
        expect(rows.length).toBeGreaterThan(0);
      }

      const followUp = journey.followUp;
      if (followUp !== undefined) {
        await page.goto("/");
        await chatPage.send(followUp.prompt);
        await chatPage.expectAssistantMessage(followUp.reply);
        await chatPage.expectIdle();
      }
    });
  });
}
