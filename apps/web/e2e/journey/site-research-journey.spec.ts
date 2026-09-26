/**
 * The researcher journey, once per named component site: a site switch, chat
 * rounds that build nothing, a one-search build, and a follow-up on the built
 * conversation. Real WDK, real Postgres, real worker; only the model is mocked.
 */

import { test, expect } from "../fixtures/a11y";
import { prompt } from "../fixtures/arcs";
import { listConversations } from "../fixtures/api-client";
import { LAYOUTS } from "../fixtures/arc-layouts";
import { expectBuild } from "../fixtures/build-checks";
import { readConversation, siteOrganism } from "../fixtures/site-reads";

/** A round the context arc answers, or one with no token that the echo answers. */
type ChatRound =
  | { readonly kind: "context"; readonly text: string }
  | { readonly kind: "echo"; readonly text: string; readonly reply: RegExp };

interface SiteJourney {
  readonly siteId: string;
  readonly title: string;
  readonly rounds: readonly ChatRound[];
  readonly followUp?: { readonly text: string; readonly reply: RegExp };
}

const JOURNEYS: readonly SiteJourney[] = [
  {
    siteId: "plasmodb",
    title: "malaria drug resistance",
    rounds: [
      {
        kind: "context",
        text: "I'm investigating chloroquine resistance mechanisms in Plasmodium falciparum",
      },
      {
        kind: "echo",
        text: "Can you help me find genes involved in drug resistance?",
        reply: /\[mock\].*Can you help/,
      },
    ],
    followUp: {
      text: "Based on these results, what pathways should I investigate?",
      reply: /\[mock\].*pathways/i,
    },
  },
  {
    siteId: "toxodb",
    title: "toxoplasma host invasion",
    rounds: [
      {
        kind: "echo",
        text: "I'm studying host cell invasion mechanisms in Toxoplasma gondii",
        reply: /\[mock\].*host cell invasion/,
      },
      {
        kind: "echo",
        text: "What micronemal and rhoptry proteins are involved in attachment?",
        reply: /\[mock\].*micronemal/i,
      },
    ],
  },
  {
    siteId: "tritrypdb",
    title: "leishmania virulence factors",
    rounds: [
      {
        kind: "context",
        text: "I'm investigating virulence factors in Leishmania major",
      },
      {
        kind: "echo",
        text: "What surface proteases are involved in host macrophage invasion?",
        reply: /\[mock\].*surface/i,
      },
    ],
    followUp: {
      text: "The strategy shows interesting protease genes, what about drug targets?",
      reply: /\[mock\].*drug targets/i,
    },
  },
  {
    siteId: "cryptodb",
    title: "cryptosporidium intestinal infection",
    rounds: [
      {
        kind: "echo",
        text: "I'm studying Cryptosporidium parvum intestinal infection mechanisms",
        reply: /\[mock\].*intestinal infection/,
      },
      {
        kind: "echo",
        text: "What oocyst wall proteins are important for environmental survival?",
        reply: /\[mock\].*oocyst/i,
      },
    ],
  },
  {
    siteId: "fungidb",
    title: "fungal pathogenesis",
    rounds: [
      {
        kind: "echo",
        text: "I'm researching antifungal drug targets in Aspergillus fumigatus",
        reply: /\[mock\].*antifungal/,
      },
      {
        kind: "echo",
        text: "What cell wall biosynthesis enzymes are potential drug targets?",
        reply: /\[mock\].*cell wall/i,
      },
      {
        kind: "echo",
        text: "Particularly interested in glucan synthase and chitin synthase",
        reply: /\[mock\].*glucan/i,
      },
    ],
    followUp: {
      text: "The strategy confirms cell wall synthesis genes, what's the clinical relevance?",
      reply: /\[mock\].*clinical/i,
    },
  },
];

for (const journey of JOURNEYS) {
  test.describe(
    `${journey.title} journey on ${journey.siteId}`,
    { tag: "@named-site" },
    () => {
      test.describe.configure({ timeout: 600_000 });

      test("chat rounds, a build and a follow-up", async ({
        chatPage,
        page,
        apiClient,
        sitePicker,
      }) => {
        await chatPage.goto();
        await sitePicker.selectSite(journey.siteId);
        await sitePicker.expectCurrentSite(journey.siteId);
        await chatPage.newChat(journey.siteId);
        const id = chatPage.lastStrategyId ?? "";

        for (const round of journey.rounds) {
          if (round.kind === "echo") {
            await chatPage.sendTurn(round.text, round.reply);
            continue;
          }
          await chatPage.sendAndSettle(prompt("context", round.text));
          await expect(page.getByTestId("data-graph-snapshot")).toHaveCount(0);
          expect((await readConversation(apiClient, id)).steps ?? []).toEqual([]);
        }

        await chatPage.sendAndSettle(
          prompt(
            "single",
            `Find ${siteOrganism(journey.siteId)} genes whose proteins have a predicted signal peptide.`,
          ),
        );
        await expectBuild(page, apiClient, id, journey.siteId, LAYOUTS.single);
        const listed = await listConversations(apiClient, journey.siteId);
        expect(listed.map((row) => row.id)).toContain(id);

        const followUp = journey.followUp;
        if (followUp !== undefined) {
          await page.goto(`/${journey.siteId}/conversation/${id}`);
          await expect(chatPage.composer).toBeVisible({ timeout: 60_000 });
          await chatPage.sendTurn(followUp.text, followUp.reply);
        }
      });
    },
  );
}
