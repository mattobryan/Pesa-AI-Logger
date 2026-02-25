package com.pesa.forwarder

data class AppConfig(
    val webhookUrl: String,
    val apiKey: String,
    val source: String,
)
