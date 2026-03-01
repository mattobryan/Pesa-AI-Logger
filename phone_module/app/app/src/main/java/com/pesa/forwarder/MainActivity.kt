package com.pesa.forwarder

import android.os.Bundle
import android.widget.Toast
import androidx.core.content.ContextCompat
import androidx.activity.ComponentActivity
import androidx.lifecycle.lifecycleScope
import com.pesa.forwarder.databinding.ActivityMainBinding
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class MainActivity : ComponentActivity() {
    private lateinit var binding: ActivityMainBinding
    private lateinit var configStore: ConfigStore
    private val webhookClient = WebhookClient()
    private var isBusy = false

    private val statusClock = SimpleDateFormat("HH:mm:ss", Locale.getDefault())
    private val neutralStatusColor by lazy { ContextCompat.getColor(this, R.color.status_neutral) }
    private val successStatusColor by lazy { ContextCompat.getColor(this, R.color.status_success) }
    private val errorStatusColor by lazy { ContextCompat.getColor(this, R.color.status_error) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        configStore = ConfigStore(this)
        bindExistingConfig()
        renderStatus(getString(R.string.status_idle))
        binding.textStatusMeta.text = getString(R.string.status_meta_idle)
        animateIntro()

        binding.buttonSave.setOnClickListener {
            saveConfigWithToast()
            renderStatus(getString(R.string.status_saved), isSuccess = true)
            updateStatusMeta(getString(R.string.status_meta_saved_prefix))
        }

        binding.buttonSendTest.setOnClickListener {
            runNetworkAction(
                actionLabel = getString(R.string.action_send_test_label),
                networkCall = { config -> webhookClient.sendTestSms(config) },
            )
        }

        binding.buttonCheckHealth.setOnClickListener {
            runNetworkAction(
                actionLabel = getString(R.string.action_health_label),
                networkCall = { config -> webhookClient.checkHealth(config) },
            )
        }

        binding.buttonClearStatus.setOnClickListener {
            renderStatus(getString(R.string.status_idle))
            binding.textStatusMeta.text = getString(R.string.status_meta_idle)
        }
    }

    private fun bindExistingConfig() {
        val config = configStore.load()
        binding.editWebhookUrl.setText(config.webhookUrl)
        binding.editApiKey.setText(config.apiKey)
        binding.editSource.setText(config.source)
    }

    private fun saveConfigWithToast() {
        configStore.save(currentConfig())
        Toast.makeText(this, getString(R.string.toast_saved), Toast.LENGTH_SHORT).show()
    }

    private fun runNetworkAction(
        actionLabel: String,
        networkCall: suspend (AppConfig) -> Result<String>,
    ) {
        if (isBusy) {
            return
        }

        val config = currentConfig()
        configStore.save(config)
        setBusy(true)
        renderStatus(getString(R.string.status_running, actionLabel))

        lifecycleScope.launch {
            val result = withContext(Dispatchers.IO) {
                networkCall(config)
            }

            result.fold(
                onSuccess = { response ->
                    renderStatus(
                        getString(R.string.status_success, actionLabel, response),
                        isSuccess = true,
                    )
                    updateStatusMeta(getString(R.string.status_meta_success_prefix))
                },
                onFailure = { error ->
                    val message = error.message ?: getString(R.string.error_unknown)
                    renderStatus(
                        getString(R.string.status_failed, actionLabel, message),
                        isError = true,
                    )
                    updateStatusMeta(getString(R.string.status_meta_failed_prefix))
                },
            )

            setBusy(false)
        }
    }

    private fun updateStatusMeta(prefix: String) {
        val time = statusClock.format(Date())
        binding.textStatusMeta.text = getString(R.string.status_meta_format, prefix, time)
    }

    private fun setBusy(busy: Boolean) {
        isBusy = busy
        binding.progressStatus.visibility = if (busy) android.view.View.VISIBLE else android.view.View.GONE
        binding.buttonSave.isEnabled = !busy
        binding.buttonSendTest.isEnabled = !busy
        binding.buttonCheckHealth.isEnabled = !busy
        binding.buttonClearStatus.isEnabled = !busy
    }

    private fun renderStatus(
        message: String,
        isError: Boolean = false,
        isSuccess: Boolean = false,
    ) {
        binding.textStatus.text = message
        binding.textStatus.setTextColor(
            when {
                isError -> errorStatusColor
                isSuccess -> successStatusColor
                else -> neutralStatusColor
            },
        )
    }

    private fun animateIntro() {
        val stagedViews = listOf(
            binding.heroPanel,
            binding.cardConfig,
            binding.cardActions,
            binding.cardStatus,
        )
        stagedViews.forEachIndexed { index, view ->
            view.alpha = 0f
            view.translationY = 32f
            view.animate()
                .alpha(1f)
                .translationY(0f)
                .setStartDelay((index * 80).toLong())
                .setDuration(360L)
                .start()
        }
    }

    private fun currentConfig(): AppConfig {
        return AppConfig(
            webhookUrl = binding.editWebhookUrl.text?.toString().orEmpty().trim(),
            apiKey = binding.editApiKey.text?.toString().orEmpty().trim(),
            source = binding.editSource.text?.toString().orEmpty().trim(),
        )
    }
}
