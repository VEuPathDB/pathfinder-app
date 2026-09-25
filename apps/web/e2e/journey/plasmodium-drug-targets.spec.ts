import { test, expect } from "../fixtures/test";
import { combineNode } from "../fixtures/ast";

test.describe("P. falciparum candidate drug-targets journey (6 turns)", () => {
  test("vague prompt -> 16-node verified strategy -> UI op-change impact", async ({
    chatPage,
    graphPage,
    sitePicker,
    apiClient,
  }) => {
    // Six turns at up to 43 s each, plus the wait for a free worker slot on
    // each one, do not fit the journey project's own budget.
    test.setTimeout(test.info().timeout + 300_000);

    await chatPage.goto();
    await sitePicker.selectSite("plasmodb");
    await chatPage.newChat("plasmodb");

    // Turn 1: vague drug-target question
    await chatPage.send(
      "I want to find candidate drug targets in Plasmodium - kinases that are expressed, don't vary much, and have no human equivalent.",
    );
    await chatPage.expectClarifyingQuestions();

    // Turn 2: user clarifies all four
    await chatPage.send(
      "Use P. falciparum 3D7. For 'expressed' use trophozoite-stage mass spec OR DeRisi microarray top 10%. For 'doesn't vary much' use dN/dS ≤ 1.3 on the Broad 3K SNP array. For 'no human equivalent' use the phylogenetic profile pattern %hsap:N%pfal:Y%.",
    );
    await chatPage.expectIdle();

    // Turn 3: broaden with InterPro + EC -> execution -> verification FAIL
    await chatPage.send(
      "Add InterPro PF00069 (Pkinase) and EC 2.7.-.- to broaden kinase identification.",
    );
    await chatPage.expectVerificationFeedback();

    // Turn 4: a fix request on a built thread is refused, not rebuilt
    // The mock's fix arc runs the build sequence again; build_strategy
    // refuses on a thread that has a strategy, and the script answers the
    // refusal instead of claiming a verification it never ran.
    await chatPage.send(
      "Fix the phylogenetic pattern by loosening to %MAMM:N%pfal:Y%.",
    );
    await chatPage.expectAssistantMessage(/Nothing was built/);
    await chatPage.expectAssistantMessage(/edit_strategy/);

    // Turn 5: UI mutation - flip the combine operator
    const conversationId = chatPage.lastStrategyId;
    expect(conversationId).toBeTruthy();
    const astUrl = `/api/v1/conversations/${conversationId as string}/ast`;
    const combine = await combineNode(await apiClient.get(astUrl));
    expect(combine.operator).toBe("UNION");
    const combineStepId = combine.id as string;

    await graphPage.goToStrategy("plasmodb", conversationId as string);
    await graphPage.expectStrategyTopbar();
    await graphPage.expectNodeVisible(combineStepId);
    await graphPage.changeOperator(combineStepId, "INTERSECT");
    await expect(graphPage.strategyPageSyncState).toHaveAttribute(
      "data-sync-state",
      "idle",
      { timeout: 30_000 },
    );
    await expect
      .poll(async () => (await combineNode(await apiClient.get(astUrl))).operator, {
        timeout: 30_000,
      })
      .toBe("INTERSECT");
    await graphPage.strategyPageBackButton.click();
    await graphPage.expectOnChatRoute(conversationId as string);

    // Turn 6: ask for impact analysis
    await chatPage.send(
      "What's the impact of switching the InterPro/GO combine to INTERSECT?",
    );
    await chatPage.expectAssistantMessage(/impact|drops|stricter|operator/i, {
      timeout: 90_000,
    });

    const resp = await apiClient.get(
      `/api/v1/conversations/${conversationId as string}`,
    );
    expect(resp.ok()).toBeTruthy();
  });
});
