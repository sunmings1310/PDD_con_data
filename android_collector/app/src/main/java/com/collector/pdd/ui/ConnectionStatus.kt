package com.collector.pdd.ui

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

object ConnectionStatus {
    data class State(
        val connected: Boolean = false,
        val message: String = "服务未连接",
    )

    private val _state = MutableStateFlow(State())
    val state: StateFlow<State> = _state

    fun mark(connected: Boolean, message: String) {
        _state.value = State(connected = connected, message = message)
    }
}
