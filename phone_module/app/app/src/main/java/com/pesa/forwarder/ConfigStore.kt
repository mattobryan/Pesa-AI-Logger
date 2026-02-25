package com.pesa.forwarder

import android.content.Context

class ConfigStore(context: Context) {
    private val prefs = context.getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE)

    fun load(): AppConfig {
        return AppConfig(
            webhookUrl = prefs.getString(KEY_WEBHOOK_URL, DEFAULT_WEBHOOK_URL).orEmpty(),
            apiKey = prefs.getString(KEY_API_KEY, "").orEmpty(),
            source = prefs.getString(KEY_SOURCE, DEFAULT_SOURCE).orEmpty(),
        )
    }

    fun save(config: AppConfig) {
        prefs.edit()
            .putString(KEY_WEBHOOK_URL, config.webhookUrl)
            .putString(KEY_API_KEY, config.apiKey)
            .putString(KEY_SOURCE, config.source)
            .apply()
    }

    companion object {
        private const val PREF_NAME = "pesa_forwarder_prefs"
        private const val KEY_WEBHOOK_URL = "webhook_url"
        private const val KEY_API_KEY = "api_key"
        private const val KEY_SOURCE = "source"

        private const val DEFAULT_WEBHOOK_URL = "http://100.123.95.105:5000/sms"
        private const val DEFAULT_SOURCE = "android-app"
    }
}
