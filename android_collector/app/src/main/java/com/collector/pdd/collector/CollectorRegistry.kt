package com.collector.pdd.collector

object CollectorRegistry {
    private val collectors = linkedMapOf<String, Collector>()

    init {
        register(PddCollector())
    }

    @Synchronized
    fun register(collector: Collector) {
        val platform = collector.platform.trim().lowercase()
        require(platform.isNotBlank()) { "collector platform must not be blank" }
        require(!collectors.containsKey(platform)) { "collector already registered: $platform" }
        collectors[platform] = collector
    }

    @Synchronized
    fun get(platform: String): Collector? = collectors[platform.trim().lowercase()]

    fun require(platform: String): Collector = get(platform)
        ?: throw CollectorException(
            SystemCollectorError.PLATFORM_NOT_SUPPORTED,
            "unsupported platform: $platform",
        )

    @Synchronized
    fun platforms(): Set<String> = collectors.keys.toSet()
}
