package com.collector.pdd.engine

import org.junit.Assert.assertEquals
import org.junit.Test

class PddPaginationTest {
    @Test
    fun choosesPreferredVisibleCardBeforePagination() {
        assertEquals(2, chooseUnseenCardIndex(listOf("a", "b", "c"), emptySet(), 2))
    }

    @Test
    fun choosesFirstUnseenCardAfterVirtualListScroll() {
        assertEquals(1, chooseUnseenCardIndex(listOf("c", "d", "e"), setOf("a", "b", "c"), -1))
        assertEquals(null, chooseUnseenCardIndex(listOf("a", "b"), setOf("a", "b"), -1))
    }
}
