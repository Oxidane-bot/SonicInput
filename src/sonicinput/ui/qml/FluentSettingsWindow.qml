import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: root
    objectName: "fluentSettingsWindow"
    title: "SonicInput Settings"
    width: 1080
    height: 760
    minimumWidth: 900
    minimumHeight: 620
    visible: false
    color: palette.window
    font.family: "Microsoft YaHei UI"

    property int selectedSection: 0
    property var viewModel: settingsViewModel
    property var sectionTitles: [
        root.t("application", "Application"),
        root.t("hotkeys", "Hotkeys"),
        root.t("transcription", "Transcription"),
        root.t("ai_processing", "AI Processing"),
        root.t("audio_and_input", "Audio and Input"),
        root.t("history", "History")
    ]

    function t(token, fallback) {
        return root.viewModel ? root.viewModel.translate(token, fallback) : fallback
    }

    function value(key, fallback) {
        return root.viewModel ? root.viewModel.value(key, fallback) : fallback
    }

    function setValue(key, value) {
        if (root.viewModel) {
            root.viewModel.setValue(key, value)
        }
    }

    function comboIndex(modelValues, value) {
        var index = modelValues.indexOf(value)
        return index >= 0 ? index : 0
    }

    function fieldText(field, key) {
        root.setValue(key, field.text)
    }

    function comboText(combo, key) {
        root.setValue(key, combo.currentText)
    }

    function comboData(combo, values, key) {
        root.setValue(key, values[combo.currentIndex])
    }

    function numberValue(control, key) {
        root.setValue(key, control.value)
    }

    function displayString(key, fallback) {
        var result = root.value(key, fallback)
        if (result === undefined || result === null) {
            return fallback
        }
        return String(result)
    }

    header: ToolBar {
        height: 48
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 18
            anchors.rightMargin: 18
            spacing: 10

            Label {
                text: "SonicInput"
                font.pixelSize: 18
                font.weight: Font.DemiBold
                Layout.fillWidth: true
            }

            Button {
                text: root.t("revert", "Revert")
                onClicked: root.viewModel && root.viewModel.reload()
            }

            Button {
                text: root.t("apply", "Apply")
                highlighted: true
                onClicked: root.viewModel && root.viewModel.apply()
            }
        }
    }

    RowLayout {
        anchors.fill: parent
        anchors.margins: 16
        spacing: 16

        Frame {
            Layout.preferredWidth: 220
            Layout.fillHeight: true
            padding: 8

            ListView {
                id: nav
                anchors.fill: parent
                spacing: 4
                clip: true
                model: root.sectionTitles
                currentIndex: root.selectedSection

                delegate: ItemDelegate {
                    width: nav.width
                    text: modelData
                    highlighted: index === root.selectedSection
                    onClicked: root.selectedSection = index
                }
            }
        }

        StackLayout {
            currentIndex: root.selectedSection
            Layout.fillWidth: true
            Layout.fillHeight: true

            Flickable {
                contentWidth: width
                contentHeight: appColumn.implicitHeight
                clip: true

                ColumnLayout {
                    id: appColumn
                    width: parent.width
                    spacing: 14

                    SettingsCard {
                        title: root.t("application", "Application")
                        GridLayout {
                            columns: 2
                            rowSpacing: 12
                            columnSpacing: 12
                            Layout.fillWidth: true

                            Label { text: root.t("language", "Language") }
                            ComboBox {
                                id: languageCombo
                                objectName: "languageCombo"
                                model: ["auto", "en-US", "zh-CN"]
                                currentIndex: root.comboIndex(model, root.value("ui.language", "auto"))
                                Layout.fillWidth: true
                                onActivated: root.comboText(languageCombo, "ui.language")
                            }

                            Label { text: root.t("theme_accent", "Theme accent") }
                            ComboBox {
                                id: themeColorCombo
                                objectName: "themeColorCombo"
                                model: ["cyan", "blue", "teal", "purple", "red", "pink", "amber"]
                                currentIndex: root.comboIndex(model, root.value("ui.theme_color", "cyan"))
                                Layout.fillWidth: true
                                onActivated: root.comboText(themeColorCombo, "ui.theme_color")
                            }

                            Label { text: root.t("log_level", "Log level") }
                            ComboBox {
                                id: logLevelCombo
                                objectName: "logLevelCombo"
                                model: ["DEBUG", "INFO", "WARNING", "ERROR"]
                                currentIndex: root.comboIndex(model, root.value("logging.level", "WARNING"))
                                Layout.fillWidth: true
                                onActivated: root.comboText(logLevelCombo, "logging.level")
                            }

                            Label { text: root.t("max_log_file_size", "Max log file size (MB)") }
                            SpinBox {
                                id: maxLogSizeSpin
                                objectName: "maxLogSizeSpin"
                                from: 1
                                to: 100
                                value: root.value("logging.max_log_size_mb", 10)
                                Layout.fillWidth: true
                                onValueModified: root.numberValue(maxLogSizeSpin, "logging.max_log_size_mb")
                            }
                        }

                        Switch {
                            text: root.t("start_minimized", "Start minimized to tray")
                            checked: root.viewModel ? root.viewModel.startMinimized : true
                            onToggled: root.viewModel && root.viewModel.setStartMinimized(checked)
                        }
                        Switch {
                            text: root.t("launch_at_login", "Launch at Windows login")
                            checked: root.viewModel ? root.viewModel.launchAtLogin : false
                            onToggled: root.viewModel && root.viewModel.setLaunchAtLogin(checked)
                        }
                        Switch {
                            text: root.t("show_tray_notifications", "Show tray notifications")
                            checked: root.viewModel ? root.viewModel.trayNotifications : true
                            onToggled: root.viewModel && root.viewModel.setTrayNotifications(checked)
                        }
                        Switch {
                            text: root.t("show_console_output", "Show console output")
                            checked: root.viewModel ? root.viewModel.consoleOutput : false
                            onToggled: root.viewModel && root.viewModel.setConsoleOutput(checked)
                        }
                    }

                    SettingsCard {
                        title: root.t("recording_overlay", "Recording Overlay")
                        GridLayout {
                            columns: 2
                            rowSpacing: 12
                            columnSpacing: 12
                            Layout.fillWidth: true

                            Label { text: root.t("preset_position", "Preset position") }
                            ComboBox {
                                id: overlayPositionCombo
                                objectName: "overlayPositionCombo"
                                model: ["center", "top_left", "top_right", "bottom_left", "bottom_right"]
                                currentIndex: root.comboIndex(model, root.value("ui.overlay_position.preset", "center"))
                                Layout.fillWidth: true
                                onActivated: {
                                    root.setValue("ui.overlay_position.mode", "preset")
                                    root.comboText(overlayPositionCombo, "ui.overlay_position.preset")
                                }
                            }
                        }
                        Switch {
                            text: root.t("show_recording_overlay", "Show recording overlay")
                            checked: root.viewModel ? root.viewModel.showOverlay : true
                            onToggled: root.viewModel && root.viewModel.setShowOverlay(checked)
                        }
                        Switch {
                            text: root.t("always_on_top", "Always on top")
                            checked: root.viewModel ? root.viewModel.overlayAlwaysOnTop : true
                            onToggled: root.viewModel && root.viewModel.setOverlayAlwaysOnTop(checked)
                        }
                        Switch {
                            text: root.t("auto_save_dragged_position", "Auto-save dragged position")
                            checked: root.value("ui.overlay_position.auto_save", true)
                            onToggled: root.setValue("ui.overlay_position.auto_save", checked)
                        }
                    }
                }
            }

            Flickable {
                contentWidth: width
                contentHeight: hotkeyColumn.implicitHeight
                clip: true

                ColumnLayout {
                    id: hotkeyColumn
                    width: parent.width
                    spacing: 14

                    SettingsCard {
                        title: root.t("registered_hotkeys", "Registered Hotkeys")
                        TextArea {
                            id: hotkeysField
                            objectName: "hotkeysField"
                            text: root.value("hotkeys.keys", ["f12"]).join("\n")
                            placeholderText: "One hotkey per line"
                            Layout.fillWidth: true
                            Layout.preferredHeight: 110
                            wrapMode: TextEdit.NoWrap
                            onEditingFinished: {
                                var lines = text.split(/\r?\n/).map(function(item) { return item.trim() }).filter(function(item) { return item.length > 0 })
                                root.setValue("hotkeys.keys", lines.length > 0 ? lines : ["f12"])
                            }
                        }
                    }

                    SettingsCard {
                        title: root.t("hotkey_backend", "Hotkey Backend")
                        ComboBox {
                            id: hotkeyBackendCombo
                            objectName: "hotkeyBackendCombo"
                            model: ["auto", "win32", "pynput"]
                            currentIndex: root.comboIndex(model, root.value("hotkeys.backend", "auto"))
                            Layout.fillWidth: true
                            onActivated: root.comboText(hotkeyBackendCombo, "hotkeys.backend")
                        }
                    }
                }
            }

            Flickable {
                contentWidth: width
                contentHeight: transcriptionColumn.implicitHeight
                clip: true

                ColumnLayout {
                    id: transcriptionColumn
                    width: parent.width
                    spacing: 14

                    SettingsCard {
                        title: root.t("transcription_provider", "Transcription Provider")
                        ComboBox {
                            id: transcriptionProviderCombo
                            objectName: "transcriptionProviderCombo"
                            model: ["local", "groq", "siliconflow", "qwen"]
                            currentIndex: root.comboIndex(model, root.value("transcription.provider", "local"))
                            Layout.fillWidth: true
                            onActivated: root.comboText(transcriptionProviderCombo, "transcription.provider")
                        }
                    }

                    SettingsCard {
                        title: root.t("local_sherpa", "Local sherpa-onnx")
                        GridLayout {
                            columns: 2
                            rowSpacing: 12
                            columnSpacing: 12
                            Layout.fillWidth: true

                            Label { text: root.t("model", "Model") }
                            ComboBox {
                                id: localModelCombo
                                objectName: "localModelCombo"
                                model: ["paraformer", "zipformer-small"]
                                currentIndex: root.comboIndex(model, root.value("transcription.local.model", "paraformer"))
                                editable: true
                                Layout.fillWidth: true
                                onAccepted: root.comboText(localModelCombo, "transcription.local.model")
                                onActivated: root.comboText(localModelCombo, "transcription.local.model")
                            }

                            Label { text: root.t("language", "Language") }
                            ComboBox {
                                id: localLanguageCombo
                                objectName: "localLanguageCombo"
                                model: ["auto", "en", "zh", "ja", "ko", "es", "fr", "de", "it", "pt", "ru"]
                                currentIndex: root.comboIndex(model, root.value("transcription.local.language", "zh"))
                                Layout.fillWidth: true
                                onActivated: root.comboText(localLanguageCombo, "transcription.local.language")
                            }

                            Label { text: root.t("streaming_mode", "Streaming mode") }
                            ComboBox {
                                id: streamingModeCombo
                                objectName: "streamingModeCombo"
                                model: ["chunked", "realtime"]
                                currentIndex: root.comboIndex(model, root.value("transcription.local.streaming_mode", "chunked"))
                                Layout.fillWidth: true
                                onActivated: root.comboText(streamingModeCombo, "transcription.local.streaming_mode")
                            }
                        }
                        Switch {
                            text: root.t("load_model_on_startup", "Load model on startup")
                            checked: root.value("transcription.local.auto_load", false)
                            onToggled: root.setValue("transcription.local.auto_load", checked)
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            Button { text: root.t("load", "Load"); onClicked: settingsHost && settingsHost.requestModelLoad(localModelCombo.currentText) }
                            Button { text: root.t("unload", "Unload"); onClicked: settingsHost && settingsHost.requestModelUnload() }
                            Button { text: root.t("test", "Test"); onClicked: settingsHost && settingsHost.requestModelTest() }
                            Item { Layout.fillWidth: true }
                        }
                    }

                    SettingsCard {
                        title: "Groq Cloud"
                        GridLayout {
                            columns: 2
                            rowSpacing: 12
                            columnSpacing: 12
                            Layout.fillWidth: true
                            Label { text: "API key" }
                            TextField { objectName: "groqApiKeyField"; echoMode: TextInput.Password; text: root.value("transcription.groq.api_key", ""); Layout.fillWidth: true; onEditingFinished: root.fieldText(this, "transcription.groq.api_key") }
                            Label { text: "Base URL" }
                            TextField { objectName: "groqBaseUrlField"; text: root.value("transcription.groq.base_url", ""); Layout.fillWidth: true; onEditingFinished: root.fieldText(this, "transcription.groq.base_url") }
                            Label { text: "Model" }
                            TextField { objectName: "groqModelField"; text: root.value("transcription.groq.model", "whisper-large-v3-turbo"); Layout.fillWidth: true; onEditingFinished: root.fieldText(this, "transcription.groq.model") }
                            Label { text: "Timeout" }
                            SpinBox { id: groqTimeoutSpin; objectName: "groqTimeoutSpin"; from: 5; to: 120; value: root.value("transcription.groq.timeout", 30); Layout.fillWidth: true; onValueModified: root.numberValue(groqTimeoutSpin, "transcription.groq.timeout") }
                            Label { text: "Max retries" }
                            SpinBox { id: groqRetriesSpin; objectName: "groqRetriesSpin"; from: 0; to: 10; value: root.value("transcription.groq.max_retries", 3); Layout.fillWidth: true; onValueModified: root.numberValue(groqRetriesSpin, "transcription.groq.max_retries") }
                        }
                    }

                    SettingsCard {
                        title: "SiliconFlow Cloud"
                        GridLayout {
                            columns: 2
                            rowSpacing: 12
                            columnSpacing: 12
                            Layout.fillWidth: true
                            Label { text: "API key" }
                            TextField { objectName: "siliconflowApiKeyField"; echoMode: TextInput.Password; text: root.value("transcription.siliconflow.api_key", ""); Layout.fillWidth: true; onEditingFinished: root.fieldText(this, "transcription.siliconflow.api_key") }
                            Label { text: "Base URL" }
                            TextField { objectName: "siliconflowBaseUrlField"; text: root.value("transcription.siliconflow.base_url", ""); Layout.fillWidth: true; onEditingFinished: root.fieldText(this, "transcription.siliconflow.base_url") }
                            Label { text: "Model" }
                            TextField { objectName: "siliconflowModelField"; text: root.value("transcription.siliconflow.model", "FunAudioLLM/SenseVoiceSmall"); Layout.fillWidth: true; onEditingFinished: root.fieldText(this, "transcription.siliconflow.model") }
                            Label { text: "Timeout" }
                            SpinBox { id: siliconflowTimeoutSpin; objectName: "siliconflowTimeoutSpin"; from: 5; to: 120; value: root.value("transcription.siliconflow.timeout", 30); Layout.fillWidth: true; onValueModified: root.numberValue(siliconflowTimeoutSpin, "transcription.siliconflow.timeout") }
                            Label { text: "Max retries" }
                            SpinBox { id: siliconflowRetriesSpin; objectName: "siliconflowRetriesSpin"; from: 0; to: 10; value: root.value("transcription.siliconflow.max_retries", 3); Layout.fillWidth: true; onValueModified: root.numberValue(siliconflowRetriesSpin, "transcription.siliconflow.max_retries") }
                        }
                    }

                    SettingsCard {
                        title: "Qwen ASR"
                        GridLayout {
                            columns: 2
                            rowSpacing: 12
                            columnSpacing: 12
                            Layout.fillWidth: true
                            Label { text: "API key" }
                            TextField { id: qwenApiKeyField; objectName: "qwenApiKeyField"; echoMode: TextInput.Password; text: root.value("transcription.qwen.api_key", ""); Layout.fillWidth: true; onEditingFinished: root.fieldText(qwenApiKeyField, "transcription.qwen.api_key") }
                            Label { text: "Base URL" }
                            TextField { objectName: "qwenBaseUrlField"; text: root.value("transcription.qwen.base_url", "https://dashscope.aliyuncs.com"); Layout.fillWidth: true; onEditingFinished: root.fieldText(this, "transcription.qwen.base_url") }
                            Label { text: "Model" }
                            TextField { objectName: "qwenModelField"; text: root.value("transcription.qwen.model", "qwen3-asr-flash"); Layout.fillWidth: true; onEditingFinished: root.fieldText(this, "transcription.qwen.model") }
                            Label { text: "Timeout" }
                            SpinBox { id: qwenTimeoutSpin; objectName: "qwenTimeoutSpin"; from: 10; to: 180; value: root.value("transcription.qwen.timeout", 30); Layout.fillWidth: true; onValueModified: root.numberValue(qwenTimeoutSpin, "transcription.qwen.timeout") }
                            Label { text: "Max retries" }
                            SpinBox { id: qwenRetriesSpin; objectName: "qwenRetriesSpin"; from: 0; to: 10; value: root.value("transcription.qwen.max_retries", 3); Layout.fillWidth: true; onValueModified: root.numberValue(qwenRetriesSpin, "transcription.qwen.max_retries") }
                        }
                        Switch {
                            text: "Enable Inverse Text Normalization"
                            checked: root.value("transcription.qwen.enable_itn", true)
                            onToggled: root.setValue("transcription.qwen.enable_itn", checked)
                        }
                    }
                }
            }

            Flickable {
                contentWidth: width
                contentHeight: aiColumn.implicitHeight
                clip: true

                ColumnLayout {
                    id: aiColumn
                    width: parent.width
                    spacing: 14

                    SettingsCard {
                        title: root.t("ai_provider", "AI Provider")
                        ComboBox {
                            id: aiProviderCombo
                            objectName: "aiProviderCombo"
                            model: ["openrouter", "groq", "nvidia", "openai_compatible"]
                            currentIndex: root.comboIndex(model, root.value("ai.provider", "openrouter"))
                            Layout.fillWidth: true
                            onActivated: root.comboText(aiProviderCombo, "ai.provider")
                        }
                    }

                    SettingsCard {
                        title: root.t("provider_credentials", "Provider Credentials")
                        GridLayout {
                            columns: 2
                            rowSpacing: 12
                            columnSpacing: 12
                            Layout.fillWidth: true
                            Label { text: "OpenRouter API key" }
                            TextField { objectName: "openrouterApiKeyField"; echoMode: TextInput.Password; text: root.value("ai.openrouter.api_key", ""); Layout.fillWidth: true; onEditingFinished: root.fieldText(this, "ai.openrouter.api_key") }
                            Label { text: "OpenRouter model" }
                            TextField { objectName: "openrouterModelField"; text: root.value("ai.openrouter.model_id", "anthropic/claude-3-sonnet"); Layout.fillWidth: true; onEditingFinished: root.fieldText(this, "ai.openrouter.model_id") }
                            Label { text: "Groq API key" }
                            TextField { objectName: "aiGroqApiKeyField"; echoMode: TextInput.Password; text: root.value("ai.groq.api_key", ""); Layout.fillWidth: true; onEditingFinished: root.fieldText(this, "ai.groq.api_key") }
                            Label { text: "Groq model" }
                            TextField { objectName: "aiGroqModelField"; text: root.value("ai.groq.model_id", "llama-3.3-70b-versatile"); Layout.fillWidth: true; onEditingFinished: root.fieldText(this, "ai.groq.model_id") }
                            Label { text: "NVIDIA API key" }
                            TextField { objectName: "nvidiaApiKeyField"; echoMode: TextInput.Password; text: root.value("ai.nvidia.api_key", ""); Layout.fillWidth: true; onEditingFinished: root.fieldText(this, "ai.nvidia.api_key") }
                            Label { text: "NVIDIA model" }
                            TextField { objectName: "nvidiaModelField"; text: root.value("ai.nvidia.model_id", "nvidia/llama-3.1-nemotron-70b-instruct"); Layout.fillWidth: true; onEditingFinished: root.fieldText(this, "ai.nvidia.model_id") }
                            Label { text: "OpenAI compatible Base URL" }
                            TextField { id: openAiCompatibleBaseUrlField; objectName: "openAiCompatibleBaseUrlField"; text: root.value("ai.openai_compatible.base_url", ""); Layout.fillWidth: true; onEditingFinished: root.fieldText(openAiCompatibleBaseUrlField, "ai.openai_compatible.base_url") }
                            Label { text: "OpenAI compatible API key" }
                            TextField { objectName: "openAiCompatibleApiKeyField"; echoMode: TextInput.Password; text: root.value("ai.openai_compatible.api_key", ""); Layout.fillWidth: true; onEditingFinished: root.fieldText(this, "ai.openai_compatible.api_key") }
                            Label { text: "OpenAI compatible model" }
                            TextField { objectName: "openAiCompatibleModelField"; text: root.value("ai.openai_compatible.model_id", "local-model"); Layout.fillWidth: true; onEditingFinished: root.fieldText(this, "ai.openai_compatible.model_id") }
                        }
                    }

                    SettingsCard {
                        title: root.t("ai_behavior", "AI Behavior")
                        Switch { text: root.t("enable_ai_optimization", "Enable AI text optimization"); checked: root.value("ai.enabled", false); onToggled: root.setValue("ai.enabled", checked) }
                        Switch { text: "Filter thinking tags"; checked: root.value("ai.filter_thinking", true); onToggled: root.setValue("ai.filter_thinking", checked) }
                        Switch { text: "Enable sentence split"; checked: root.value("ai.sentence_split.enabled", false); onToggled: root.setValue("ai.sentence_split.enabled", checked) }
                        Switch { text: "Start AI after first ASR chunk"; checked: root.value("ai.first_chunk_output.enabled", false); onToggled: root.setValue("ai.first_chunk_output.enabled", checked) }
                        Switch { text: "Enable AI streaming output"; checked: root.value("ai.streaming_enabled", false); onToggled: root.setValue("ai.streaming_enabled", checked) }
                        GridLayout {
                            columns: 2
                            rowSpacing: 12
                            columnSpacing: 12
                            Layout.fillWidth: true
                            Label { text: "Timeout" }
                            SpinBox { id: aiTimeoutSpin; objectName: "aiTimeoutSpin"; from: 5; to: 120; value: root.value("ai.timeout", 30); Layout.fillWidth: true; onValueModified: root.numberValue(aiTimeoutSpin, "ai.timeout") }
                            Label { text: "Max retries" }
                            SpinBox { id: aiRetriesSpin; objectName: "aiRetriesSpin"; from: 0; to: 5; value: root.value("ai.retries", 3); Layout.fillWidth: true; onValueModified: root.numberValue(aiRetriesSpin, "ai.retries") }
                        }
                        TextArea {
                            id: aiPromptField
                            objectName: "aiPromptField"
                            text: root.value("ai.prompt", "")
                            placeholderText: "System prompt"
                            Layout.fillWidth: true
                            Layout.preferredHeight: 170
                            wrapMode: TextEdit.WordWrap
                            onEditingFinished: root.fieldText(aiPromptField, "ai.prompt")
                        }
                    }
                }
            }

            Flickable {
                contentWidth: width
                contentHeight: audioColumn.implicitHeight
                clip: true

                ColumnLayout {
                    id: audioColumn
                    width: parent.width
                    spacing: 14

                    SettingsCard {
                        title: root.t("audio_device", "Audio Device")
                        RowLayout {
                            Layout.fillWidth: true
                            TextField {
                                id: audioDeviceField
                                objectName: "audioDeviceField"
                                text: root.displayString("audio.device_id", "")
                                placeholderText: root.t("system_default", "System default")
                                Layout.fillWidth: true
                                onEditingFinished: root.fieldText(audioDeviceField, "audio.device_id")
                            }
                            Button { text: root.t("refresh", "Refresh") }
                        }
                    }

                    SettingsCard {
                        title: root.t("streaming_transcription", "Streaming Transcription")
                        Slider {
                            id: chunkDurationSlider
                            objectName: "chunkDurationSlider"
                            from: 5
                            to: 60
                            stepSize: 0.5
                            value: root.value("audio.streaming.chunk_duration", 15)
                            Layout.fillWidth: true
                            onMoved: root.numberValue(chunkDurationSlider, "audio.streaming.chunk_duration")
                        }
                        Label { text: root.t("chunk_duration", "Chunk duration") + ": " + chunkDurationSlider.value.toFixed(1) + " seconds" }
                    }

                    SettingsCard {
                        title: root.t("text_input", "Text Input")
                        GridLayout {
                            columns: 2
                            rowSpacing: 12
                            columnSpacing: 12
                            Layout.fillWidth: true
                            Label { text: root.t("preferred_method", "Preferred method") }
                            ComboBox {
                                id: inputMethodCombo
                                objectName: "inputMethodCombo"
                                model: ["clipboard", "sendinput"]
                                currentIndex: root.comboIndex(model, root.value("input.preferred_method", "clipboard"))
                                Layout.fillWidth: true
                                onActivated: root.comboText(inputMethodCombo, "input.preferred_method")
                            }
                            Label { text: "Clipboard restore delay (ms)" }
                            SpinBox { id: clipboardDelaySpin; objectName: "clipboardDelaySpin"; from: 0; to: 10000; value: Math.round(root.value("input.clipboard_restore_delay", 0.5) * 1000); Layout.fillWidth: true; onValueModified: root.setValue("input.clipboard_restore_delay", clipboardDelaySpin.value / 1000.0) }
                            Label { text: "Typing delay (ms)" }
                            SpinBox { id: typingDelaySpin; objectName: "typingDelaySpin"; from: 0; to: 1000; value: Math.round(root.value("input.typing_delay", 0.01) * 1000); Layout.fillWidth: true; onValueModified: root.setValue("input.typing_delay", typingDelaySpin.value / 1000.0) }
                        }
                        Switch { text: root.t("enable_fallback", "Enable fallback to alternative method"); checked: root.value("input.fallback_enabled", true); onToggled: root.setValue("input.fallback_enabled", checked) }
                        Switch { text: root.t("auto_detect_terminal", "Auto-detect terminal applications"); checked: root.value("input.auto_detect_terminal", true); onToggled: root.setValue("input.auto_detect_terminal", checked) }
                    }
                }
            }

            Flickable {
                contentWidth: width
                contentHeight: historyColumn.implicitHeight
                clip: true

                ColumnLayout {
                    id: historyColumn
                    width: parent.width
                    spacing: 14

                    SettingsCard {
                        title: root.t("history", "History")
                        RowLayout {
                            Layout.fillWidth: true
                            TextField {
                                id: historySearchField
                                objectName: "historySearchField"
                                placeholderText: root.t("search_history", "Search in transcription or AI text")
                                Layout.fillWidth: true
                            }
                            Button { text: root.t("refresh", "Refresh") }
                            Button { text: root.t("batch_reprocess", "Batch Reprocess") }
                        }

                        ListView {
                            objectName: "historyList"
                            Layout.fillWidth: true
                            Layout.preferredHeight: 320
                            clip: true
                            model: [root.t("no_history_records_loaded", "No history records loaded")]
                            delegate: ItemDelegate { width: parent ? parent.width : 0; text: modelData }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            Label { text: "Total Records: 0" }
                            Label { text: "Total Duration: 0.0s" }
                            Label { text: "Success Rate: 0%" }
                            Item { Layout.fillWidth: true }
                        }
                    }
                }
            }
        }
    }
}
