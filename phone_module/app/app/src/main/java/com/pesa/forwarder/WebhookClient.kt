package com.pesa.forwarder

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject

class WebhookClient(
    private val httpClient: OkHttpClient = OkHttpClient(),
) {
    fun sendTestSms(config: AppConfig): Result<String> {
        val url = config.webhookUrl.trim()
        if (url.isBlank()) {
            return Result.failure(IllegalArgumentException("Webhook URL is required"))
        }

        val payload = JSONObject()
            .put(
                "sms",
                "UBTEST123 Confirmed. Ksh50.00 sent to TEST USER 0700000000 on 25/2/26 at 10:30 AM. New M-PESA balance is Ksh500.00. Transaction cost, Ksh0.00.",
            )
            .put("source", config.source.ifBlank { "android-app" })
            .toString()

        val body = payload.toRequestBody("application/json; charset=utf-8".toMediaType())
        val requestBuilder = Request.Builder()
            .url(url)
            .post(body)
            .addHeader("Content-Type", "application/json")

        val key = config.apiKey.trim()
        if (key.isNotEmpty()) {
            requestBuilder.addHeader("X-API-Key", key)
        }

        return runCatching {
            httpClient.newCall(requestBuilder.build()).execute().use { response ->
                val responseBody = response.body?.string().orEmpty()
                "HTTP ${response.code}: ${responseBody.take(300)}"
            }
        }
    }
}
