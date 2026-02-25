package com.pesa.forwarder

import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.lifecycle.lifecycleScope
import com.pesa.forwarder.databinding.ActivityMainBinding
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class MainActivity : ComponentActivity() {
    private lateinit var binding: ActivityMainBinding
    private lateinit var configStore: ConfigStore
    private val webhookClient = WebhookClient()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        configStore = ConfigStore(this)
        bindExistingConfig()

        binding.buttonSave.setOnClickListener {
            val config = currentConfig()
            configStore.save(config)
            binding.textStatus.text = "Status: settings saved"
            Toast.makeText(this, "Settings saved", Toast.LENGTH_SHORT).show()
        }

        binding.buttonSendTest.setOnClickListener {
            val config = currentConfig()
            configStore.save(config)
            binding.textStatus.text = "Status: sending test payload..."

            lifecycleScope.launch {
                val result = withContext(Dispatchers.IO) {
                    webhookClient.sendTestSms(config)
                }
                binding.textStatus.text = result.fold(
                    onSuccess = { "Status: $it" },
                    onFailure = { "Status: failed - ${it.message}" },
                )
            }
        }
    }

    private fun bindExistingConfig() {
        val config = configStore.load()
        binding.editWebhookUrl.setText(config.webhookUrl)
        binding.editApiKey.setText(config.apiKey)
        binding.editSource.setText(config.source)
    }

    private fun currentConfig(): AppConfig {
        return AppConfig(
            webhookUrl = binding.editWebhookUrl.text?.toString().orEmpty().trim(),
            apiKey = binding.editApiKey.text?.toString().orEmpty().trim(),
            source = binding.editSource.text?.toString().orEmpty().trim(),
        )
    }
}
