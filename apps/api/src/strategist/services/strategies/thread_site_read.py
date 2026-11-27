from uuid import UUID

from assistant_core.platform.db import DBSessionFactory
from veupathdb.wdk import WDKStrategyDetails

from strategist.domain.strategy.session import StrategySession
from strategist.services.strategies.context import StrategyMutationContext
from strategist.services.strategies.gene_set_refresh import defer_the_gene_set_refresh
from strategist.services.strategies.live_counts import (
    SiteRead,
    read_the_live_strategy,
    site_read,
)
from strategist.services.strategies.persist import (
    persist_strategy_ast_to_conversation,
)
from strategist.services.strategies.session_factory import stored_strategy_session
from strategist.services.strategies.site_changes import take_what_the_site_holds
from strategist.services.strategies.sync_state import ensure_sync_state
from strategist.services.strategies.write_lock import strategy_write_lock


async def read_the_site_into_the_thread(
    *,
    session: StrategySession,
    conversation_id: UUID,
    db_session_factory: DBSessionFactory,
) -> SiteRead:
    """Store what the site moved on the thread's strategy, and hand ``session`` it.

    The stored graph is read again under the thread's write lock, so the site's
    edit lands on the tree the last writer left. A thread with no steps has
    nothing the site can move, so its read takes no lock. The answer is the
    site's strategy, and why the site or its tree was not read.
    """
    held = session.sync_state
    if held is None or held.wdk_strategy_id is None or not held.wdk_step_ids:
        return SiteRead()
    graph = session.get_graph(None)
    if graph is None or not graph.steps:
        return site_read(await read_the_live_strategy(held, session.site_id))
    async with strategy_write_lock(conversation_id, db_session_factory) as locked:
        stored = await stored_strategy_session(locked, conversation_id, session.site_id)
        stored_graph = None if stored is None else stored.get_graph(None)
        if stored is None or stored_graph is None:
            return SiteRead()
        sync_state = ensure_sync_state(stored)
        match await read_the_live_strategy(sync_state, session.site_id):
            case WDKStrategyDetails() as live:
                pass
            case unread:
                return site_read(unread)
        edits = await take_what_the_site_holds(
            graph=stored_graph,
            sync_state=sync_state,
            site_id=session.site_id,
            live=live,
        )
        if not edits.moved:
            return SiteRead(live=live, not_read=edits.not_read)
        written = StrategyMutationContext(
            site_id=session.site_id,
            strategy_session=stored,
            conversation_id=conversation_id,
            locked_session=locked,
        )
        await persist_strategy_ast_to_conversation(
            deps=written, graph=stored_graph, sync_result=None
        )
        await defer_the_gene_set_refresh(written)
    session.graph = stored_graph
    session.sync_state = sync_state
    return SiteRead(live=live, not_read=edits.not_read)
