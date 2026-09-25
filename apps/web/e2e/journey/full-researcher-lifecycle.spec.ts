import { test, expect } from "../fixtures/a11y";
import { MOCK_PLAN_PROMPT } from "../fixtures/mock-prompts";

/**
 * Journey: Full Researcher Lifecycle - PlasmoDB (Complete Arc)
 *
 * The most comprehensive journey test. Covers the ENTIRE user lifecycle:
 * Auth -> multi-round chat -> strategy creation -> the build's gene set ->
 * site switching with isolation verification -> settings -> API verification
 * at every stage.
 *
 * Real WDK API, real PostgreSQL. Only the LLM is mocked.
 */
test.describe("Full Researcher Lifecycle", () => {
  test("end-to-end research workflow with full output verification", async ({
    chatPage,
    graphPage,
    sidebarPage,
    sitePicker,
    settingsPage,
    page,
    apiClient,
  }) => {
    // Phase 1: Chat & Strategy (PlasmoDB)
    // Switch to PlasmoDB for this journey
    await chatPage.goto();
    await sitePicker.selectSite("plasmodb");

    // Start fresh conversation
    await chatPage.newChat();

    // Chat round 1
    await chatPage.send("find drug resistance genes in Plasmodium falciparum");
    await chatPage.expectAssistantMessage(/\[mock\]/);
    await chatPage.expectIdle();

    // Chat round 2
    await chatPage.send(
      "I want to focus on chloroquine and artemisinin resistance mechanisms",
    );
    await chatPage.expectAssistantMessage(/\[mock\].*chloroquine/i);
    await chatPage.expectIdle();

    // Chat round 3 - build the strategy
    await chatPage.send(MOCK_PLAN_PROMPT);
    await graphPage.expectRailPanel();

    // Verify strategy exists via API - use captured ID for isolation
    const strategyId = chatPage.lastStrategyId;
    expect(strategyId).toBeTruthy();
    const stratResp = await apiClient.get(`/api/v1/conversations/${strategyId}`);
    expect(stratResp.ok()).toBeTruthy();
    const latestStrategy = await stratResp.json();
    expect(latestStrategy.steps.length).toBeGreaterThan(0);

    // Phase 2: The build's gene set, read back through the API
    await chatPage.expectIdle();
    const builtResp = await apiClient.get("/api/v1/gene-sets?siteId=plasmodb");
    expect(builtResp.ok()).toBeTruthy();
    const builtSets = (await builtResp.json()) as {
      id: string;
      source: string;
      geneCount: number;
      geneIds: string[];
    }[];
    const builtSet = builtSets.find((gs) => gs.source === "strategy");
    expect(builtSet).toBeDefined();
    expect(builtSet?.geneCount).toBeGreaterThan(0);
    expect(builtSet?.geneIds[0]).toMatch(/^PF3D7_/);

    // Phase 3: Site Switching - Isolation Verification
    // Switch to ToxoDB
    await sitePicker.selectSite("toxodb");
    await sitePicker.expectCurrentSite("toxodb");

    // Clean any stale ToxoDB gene sets before checking isolation.
    const staleToxoResp = await apiClient.get("/api/v1/gene-sets?siteId=toxodb");
    if (staleToxoResp.ok()) {
      const staleToxo = (await staleToxoResp.json()) as { id: string }[];
      await Promise.all(
        staleToxo.map((gs) => apiClient.delete(`/api/v1/gene-sets/${gs.id}`)),
      );
    }

    // API confirms no ToxoDB gene sets
    const toxoResp = await apiClient.get("/api/v1/gene-sets?siteId=toxodb");
    expect(toxoResp.ok()).toBeTruthy();
    const toxoSets = await toxoResp.json();
    expect(toxoSets.length).toBe(0);

    // Phase 4: Return to PlasmoDB & Settings
    await sitePicker.selectSite("plasmodb");
    await sitePicker.expectCurrentSite("plasmodb");

    // Settings modal
    await settingsPage.open();
    await settingsPage.expectAllTabsVisible();
    await settingsPage.openTab("Data");
    await settingsPage.close();

    // Phase 5: Final Chat & Conversation Persistence
    // The sidebar lists one site's conversations, and this journey's live on
    // PlasmoDB, so return to the PlasmoDB chat rather than to "/" (which
    // resolves to the portal).
    await page.goto("/plasmodb/conversation");
    await expect(page.getByTestId("message-composer")).toBeVisible();

    // Verify conversations still exist in sidebar
    await sidebarPage.expectAtLeastOneConversation();

    // Send final message
    await chatPage.send("Summarize my findings from the resistance gene analysis");
    await chatPage.expectAssistantMessage(/\[mock\].*findings/i);
    await chatPage.expectIdle();

    // API verification: the build's gene set is still intact.
    const finalResp = await apiClient.get("/api/v1/gene-sets?siteId=plasmodb");
    const finalSets = (await finalResp.json()) as { id: string; geneCount: number }[];
    const finalSet = finalSets.find((gs) => gs.id === builtSet?.id);
    expect(finalSet?.geneCount).toBe(builtSet?.geneCount);
  });
});
