package com.pesa.forwarder

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import org.json.JSONObject

class WebhookClient(
    private val httpClient: OkHttpClient = OkHttpClient(),
) {
    fun sendTestSms(config: AppConfig): Result<String> {
        val smsUrl = config.webhookUrl.trim()
        if (smsUrl.isBlank()) {
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
            .url(smsUrl)
            .post(body)
            .addHeader("Content-Type", "application/json")

        attachApiKey(requestBuilder, config)

        return execute(requestBuilder, successCodes = setOf(200, 201, 422))
    }

    fun checkHealth(config: AppConfig): Result<String> {
        val smsUrl = config.webhookUrl.trim()
        if (smsUrl.isBlank()) {
            return Result.failure(IllegalArgumentException("Webhook URL is required"))
        }

        val healthUrl = deriveHealthUrl(smsUrl)
            ?: return Result.failure(
                IllegalArgumentException("Invalid webhook URL. Example: http://127.0.0.1:5000/sms"),
            )

        val requestBuilder = Request.Builder()
            .url(healthUrl)
            .get()
            .addHeader("Accept", "application/json")

        attachApiKey(requestBuilder, config)
        return execute(requestBuilder, successCodes = setOf(200))
    }

    private fun attachApiKey(requestBuilder: Request.Builder, config: AppConfig) {
        val key = config.apiKey.trim()
        if (key.isNotEmpty()) {
            requestBuilder.addHeader("X-API-Key", key)
        }
    }

    private fun execute(
        requestBuilder: Request.Builder,
        successCodes: Set<Int>,
    ): Result<String> {
        return runCatching {
            httpClient.newCall(requestBuilder.build()).execute().use { response ->
                val responseBody = response.body?.string().orEmpty()
                val bodyPreview = responseBody.take(400)
                val summary = "HTTP ${response.code}: $bodyPreview"
                if (response.code !in successCodes) {
                    throw IllegalStateException(summary)
                }
                summary
            }
        }
    }

    private fun deriveHealthUrl(webhookUrl: String): String? {
        val parsed = webhookUrl.toHttpUrlOrNull() ?: return null
        return parsed.newBuilder()
            .encodedPath("/health")
            .query(null)
            .build()
            .toString()
    }
}
