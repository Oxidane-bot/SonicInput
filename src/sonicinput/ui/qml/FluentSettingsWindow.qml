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
    property string selectedTranscriptionProvider: root.viewModel ? root.viewModel.transcriptionProvider : "local"
    property string selectedAiProvider: root.viewModel ? root.viewModel.aiProvider : "openrouter"
    property bool hotkeyCaptureVisible: false
    property int hotkeyCaptureIndex: -1
    property string hotkeyCaptureValue: ""
    property string hotkeyCaptureMessage: ""
    property string hotkeyCaptureMode: "add"
    property var sectionTitles: [
        root.t("application", "Application"),
        root.t("hotkeys", "Hotkeys"),
        root.t("transcription", "Transcription"),
        root.t("ai_processing", "AI Processing"),
        root.t("audio_and_input", "Audio and Input"),
        root.t("history", "History")
    ]

    function t(token, fallback) {
        var language = root.viewModel ? root.viewModel.uiLanguage : "en-US"
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

    function modelValueIndex(modelObject, value) {
        for (var i = 0; i < modelObject.count; i++) {
            if (modelObject.get(i).value === value) {
                return i
            }
        }
        return 0
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

    function hotkeyLabelText(value) {
        var parts = String(value).split("+")
        return parts.map(function(item) {
            var token = item.trim()
            if (!token.length) {
                return token
            }
            if (token.length === 1) {
                return token.toUpperCase()
            }
            return token.charAt(0).toUpperCase() + token.slice(1)
        }).join(" + ")
    }

    function hotkeyCandidateModifiers(modifiers) {
        var tokens = []
        if (modifiers & Qt.ControlModifier) {
            tokens.push("ctrl")
        }
        if (modifiers & Qt.ShiftModifier) {
            tokens.push("shift")
        }
        if (modifiers & Qt.AltModifier) {
            tokens.push("alt")
        }
        if (modifiers & Qt.MetaModifier) {
            tokens.push("win")
        }
        return tokens
    }

    function hotkeyCandidateKey(key, text) {
        if (key >= Qt.Key_A && key <= Qt.Key_Z) {
            return String.fromCharCode(key).toLowerCase()
        }
        if (key >= Qt.Key_0 && key <= Qt.Key_9) {
            return String.fromCharCode(key)
        }
        if (key >= Qt.Key_F1 && key <= Qt.Key_F35) {
            return "f" + (key - Qt.Key_F1 + 1)
        }

        var namedKeys = {}
        namedKeys[Qt.Key_Space] = "space"
        namedKeys[Qt.Key_Tab] = "tab"
        namedKeys[Qt.Key_Backtab] = "tab"
        namedKeys[Qt.Key_Return] = "enter"
        namedKeys[Qt.Key_Enter] = "enter"
        namedKeys[Qt.Key_Escape] = "escape"
        namedKeys[Qt.Key_Backspace] = "backspace"
        namedKeys[Qt.Key_Delete] = "delete"
        namedKeys[Qt.Key_Insert] = "insert"
        namedKeys[Qt.Key_Home] = "home"
        namedKeys[Qt.Key_End] = "end"
        namedKeys[Qt.Key_PageUp] = "pageup"
        namedKeys[Qt.Key_PageDown] = "pagedown"
        namedKeys[Qt.Key_Left] = "left"
        namedKeys[Qt.Key_Right] = "right"
        namedKeys[Qt.Key_Up] = "up"
        namedKeys[Qt.Key_Down] = "down"
        namedKeys[Qt.Key_Plus] = "+"
        namedKeys[Qt.Key_Minus] = "-"

        if (namedKeys[key]) {
            return namedKeys[key]
        }

        if (text && text.length === 1) {
            return text.toLowerCase()
        }

        return ""
    }

    function hotkeyFromEvent(event) {
        if (!event) {
            return ""
        }

        if (event.key === Qt.Key_Escape) {
            return "__cancel__"
        }

        var mainKey = hotkeyCandidateKey(event.key, event.text)
        if (!mainKey || mainKey === "+" || mainKey === "-") {
            return ""
        }

        var parts = hotkeyCandidateModifiers(event.modifiers)
        parts.push(mainKey)
        return parts.join("+")
    }

    function beginHotkeyCapture(index) {
        root.hotkeyCaptureVisible = true
        root.hotkeyCaptureIndex = index
        root.hotkeyCaptureMode = index >= 0 ? "edit" : "add"
        root.hotkeyCaptureValue = ""
        root.hotkeyCaptureMessage = root.t("capture_ready", "Ready to record a shortcut")
        hotkeyRecorderSurface.forceActiveFocus()
    }

    function cancelHotkeyCapture() {
        root.hotkeyCaptureVisible = false
        root.hotkeyCaptureIndex = -1
        root.hotkeyCaptureMode = "add"
        root.hotkeyCaptureValue = ""
        root.hotkeyCaptureMessage = ""
    }

    function commitHotkeyCapture(value) {
        if (!root.viewModel) {
            root.hotkeyCaptureMessage = root.t("capture_unavailable", "Unable to record shortcuts right now.")
            return
        }

        var result = root.hotkeyCaptureIndex >= 0
            ? root.viewModel.replaceHotkey(value, root.hotkeyCaptureIndex)
            : root.viewModel.addHotkey(value)

        if (result && result.success) {
            cancelHotkeyCapture()
        } else if (result && result.message) {
            root.hotkeyCaptureMessage = result.message
        } else {
            root.hotkeyCaptureMessage = root.t("capture_failed", "Unable to start recording, please try again.")
        }
    }

    function removeHotkey(index) {
        if (!root.viewModel) {
            return
        }
        root.viewModel.removeHotkeyAt(index)
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

    function historyDetailValue(key, fallback) {
        if (!root.viewModel || !root.viewModel.selectedHistoryDetail) {
            return fallback
        }
        var value = root.viewModel.selectedHistoryDetail[key]
        if (value === undefined || value === null) {
            return fallback
        }
        return String(value)
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
                objectName: "revertButton"
                text: root.t("revert", "Revert")
                onClicked: root.viewModel && root.viewModel.reload()
            }

            Button {
                objectName: "applyButton"
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
                objectName: "applicationPage"
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
                objectName: "hotkeysPage"
                contentWidth: width
                contentHeight: hotkeyColumn.implicitHeight
                clip: true

                ColumnLayout {
                    id: hotkeyColumn
                    width: parent.width
                    spacing: 14

                    SettingsCard {
                        title: root.t("registered_hotkeys", "Registered Hotkeys")
                        ColumnLayout {
                            objectName: "hotkeysToolbar"
                            Layout.fillWidth: true
                            spacing: 12

                            RowLayout {
                                Layout.fillWidth: true

                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 2

                                    Label {
                                        text: root.t("active_hotkeys", "Active hotkeys")
                                        font.pixelSize: 13
                                        font.weight: Font.Medium
                                    }

                                    Label {
                                        text: root.t("shortcut_count", "Bound {count}").replace("{count}", root.viewModel ? root.viewModel.hotkeyCount : 0)
                                        opacity: 0.62
                                        font.pixelSize: 12
                                    }
                                }

                                Button {
                                    id: hotkeyCaptureButton
                                    objectName: "hotkeyCaptureButton"
                                    text: root.t("add_shortcut", "Add shortcut")
                                    onClicked: root.beginHotkeyCapture(-1)
                                }
                            }

                            Rectangle {
                                Layout.fillWidth: true
                                Layout.preferredHeight: Math.max(156, Math.min(264, hotkeysListView.contentHeight + 18))
                                radius: 8
                                color: palette.base
                                border.color: palette.mid
                                border.width: 1
                                clip: true

                                ListView {
                                    id: hotkeysListView
                                    objectName: "hotkeysListView"
                                    anchors.fill: parent
                                    anchors.margins: 8
                                    spacing: 6
                                    clip: true
                                    model: root.viewModel ? root.viewModel.hotkeyList : ["f12"]

                                    delegate: Rectangle {
                                        width: ListView.view.width
                                        height: 46
                                        radius: 8
                                        color: palette.window
                                        border.color: palette.mid
                                        border.width: 1

                                        RowLayout {
                                            anchors.fill: parent
                                            anchors.margins: 8
                                            spacing: 8

                                            ColumnLayout {
                                                Layout.fillWidth: true
                                                spacing: 2

                                                Label {
                                                    text: root.hotkeyLabelText(modelData)
                                                    font.pixelSize: 13
                                                    font.weight: Font.DemiBold
                                                    elide: Text.ElideRight
                                                }

                                                Label {
                                                    text: root.t("selected_hotkey", "Selected hotkey")
                                                    opacity: 0.58
                                                    font.pixelSize: 11
                                                }
                                            }

                                            Button {
                                                id: hotkeyDelegateChangeButton
                                                objectName: "hotkeyDelegateChangeButton"
                                                text: root.t("change", "Change")
                                                onClicked: root.beginHotkeyCapture(index)
                                            }

                                            Button {
                                                id: hotkeyDelegateRemoveButton
                                                objectName: "hotkeyDelegateRemoveButton"
                                                text: root.t("remove", "Remove")
                                                enabled: root.viewModel ? root.viewModel.hotkeyCount > 1 : false
                                                onClicked: root.removeHotkey(index)
                                            }
                                        }
                                    }
                                }
                            }

                            FocusScope {
                                id: hotkeyRecorderSurface
                                objectName: "hotkeyCapturePanel"
                                visible: root.hotkeyCaptureVisible
                                focus: root.hotkeyCaptureVisible
                                Layout.fillWidth: true
                                Layout.preferredHeight: 132

                                Keys.onPressed: function(event) {
                                    var hotkey = root.hotkeyFromEvent(event)
                                    if (hotkey === "__cancel__") {
                                        root.cancelHotkeyCapture()
                                        event.accepted = true
                                        return
                                    }
                                    if (!hotkey) {
                                        event.accepted = true
                                        return
                                    }

                                    root.hotkeyCaptureValue = hotkey
                                    root.commitHotkeyCapture(hotkey)
                                    event.accepted = true
                                }

                                    Rectangle {
                                    anchors.fill: parent
                                    objectName: "hotkeyRecorderSurface"
                                    radius: 8
                                    color: palette.base
                                    border.color: palette.mid
                                    border.width: 1
                                }

                                ColumnLayout {
                                    anchors.fill: parent
                                    anchors.margins: 14
                                    spacing: 10

                                    RowLayout {
                                        Layout.fillWidth: true

                                        Label {
                                            text: root.hotkeyCaptureIndex >= 0
                                                ? root.t("edit_shortcut", "Edit shortcut")
                                                : root.t("add_shortcut", "Add shortcut")
                                            font.pixelSize: 13
                                            font.weight: Font.Medium
                                        }

                                        Item { Layout.fillWidth: true }

                                        Label {
                                            text: root.t("capture_cancel_hint", "Press Esc to cancel")
                                            opacity: 0.72
                                            font.pixelSize: 12
                                        }
                                    }

                                    Label {
                                        id: hotkeyCaptureChip
                                        text: root.hotkeyCaptureValue.length > 0
                                            ? root.hotkeyLabelText(root.hotkeyCaptureValue)
                                            : root.t("capture_ready", "Ready to record a shortcut")
                                        font.pixelSize: 12
                                        font.weight: Font.Medium
                                        padding: 10
                                        background: Rectangle {
                                            radius: 7
                                            color: palette.window
                                            border.color: palette.mid
                                            border.width: 1
                                        }
                                    }

                                    Label {
                                        id: hotkeyStatusLabel
                                        objectName: "hotkeyStatusLabel"
                                        text: root.hotkeyCaptureMessage.length > 0
                                            ? root.hotkeyCaptureMessage
                                            : root.t("capture_idle_hint", "Click add or change to record a new shortcut")
                                        opacity: 0.66
                                        wrapMode: Text.WordWrap
                                        Layout.fillWidth: true
                                    }
                                }
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
                objectName: "transcriptionPage"
                contentWidth: width
                contentHeight: transcriptionColumn.implicitHeight
                clip: true

                ColumnLayout {
                    id: transcriptionColumn
                    width: parent.width
                    spacing: 14

                    SettingsCard {
                        title: root.t("transcription_provider", "Transcription Provider")
                        ListModel {
                            id: transcriptionProviderModel
                            ListElement { value: "local"; label: "Local (sherpa-onnx)" }
                            ListElement { value: "groq"; label: "Groq Cloud" }
                            ListElement { value: "siliconflow"; label: "SiliconFlow Cloud" }
                            ListElement { value: "qwen"; label: "Qwen ASR (Alibaba Cloud)" }
                        }
                        ComboBox {
                            id: transcriptionProviderCombo
                            objectName: "transcriptionProviderCombo"
                            textRole: "label"
                            valueRole: "value"
                            model: transcriptionProviderModel
                            currentIndex: root.modelValueIndex(transcriptionProviderModel, root.selectedTranscriptionProvider)
                            Layout.fillWidth: true
                            onActivated: {
                                root.selectedTranscriptionProvider = transcriptionProviderCombo.currentValue
                                root.setValue("transcription.provider", transcriptionProviderCombo.currentValue)
                            }
                        }
                    }

                    SettingsCard {
                        objectName: "localTranscriptionCard"
                        title: root.t("local_sherpa", "Local sherpa-onnx")
                        visible: root.selectedTranscriptionProvider === "local"
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
                        objectName: "groqTranscriptionCard"
                        title: "Groq Cloud"
                        visible: root.selectedTranscriptionProvider === "groq"
                        GridLayout {
                            columns: 2
                            rowSpacing: 12
                            columnSpacing: 12
                            Layout.fillWidth: true
                            Label { text: root.t("api_key", "API key") }
                            TextField { objectName: "groqApiKeyField"; echoMode: TextInput.Password; text: root.value("transcription.groq.api_key", ""); Layout.fillWidth: true; onEditingFinished: root.fieldText(this, "transcription.groq.api_key") }
                            Label { text: root.t("base_url", "Base URL") }
                            TextField { objectName: "groqBaseUrlField"; placeholderText: root.t("leave_empty_default", "Leave empty to use the default"); text: root.value("transcription.groq.base_url", ""); Layout.fillWidth: true; onEditingFinished: root.fieldText(this, "transcription.groq.base_url") }
                            Label { text: root.t("model", "Model") }
                            TextField { objectName: "groqModelField"; text: root.value("transcription.groq.model", "whisper-large-v3-turbo"); Layout.fillWidth: true; onEditingFinished: root.fieldText(this, "transcription.groq.model") }
                            Label { text: root.t("timeout", "Timeout") }
                            SpinBox { id: groqTimeoutSpin; objectName: "groqTimeoutSpin"; from: 5; to: 120; value: root.value("transcription.groq.timeout", 30); Layout.fillWidth: true; onValueModified: root.numberValue(groqTimeoutSpin, "transcription.groq.timeout") }
                            Label { text: root.t("max_retries", "Max retries") }
                            SpinBox { id: groqRetriesSpin; objectName: "groqRetriesSpin"; from: 0; to: 10; value: root.value("transcription.groq.max_retries", 3); Layout.fillWidth: true; onValueModified: root.numberValue(groqRetriesSpin, "transcription.groq.max_retries") }
                        }
                    }

                    SettingsCard {
                        objectName: "siliconflowTranscriptionCard"
                        title: "SiliconFlow Cloud"
                        visible: root.selectedTranscriptionProvider === "siliconflow"
                        GridLayout {
                            columns: 2
                            rowSpacing: 12
                            columnSpacing: 12
                            Layout.fillWidth: true
                            Label { text: root.t("api_key", "API key") }
                            TextField { objectName: "siliconflowApiKeyField"; echoMode: TextInput.Password; text: root.value("transcription.siliconflow.api_key", ""); Layout.fillWidth: true; onEditingFinished: root.fieldText(this, "transcription.siliconflow.api_key") }
                            Label { text: root.t("base_url", "Base URL") }
                            TextField { objectName: "siliconflowBaseUrlField"; placeholderText: root.t("leave_empty_default", "Leave empty to use the default"); text: root.value("transcription.siliconflow.base_url", ""); Layout.fillWidth: true; onEditingFinished: root.fieldText(this, "transcription.siliconflow.base_url") }
                            Label { text: root.t("model", "Model") }
                            TextField { objectName: "siliconflowModelField"; text: root.value("transcription.siliconflow.model", "FunAudioLLM/SenseVoiceSmall"); Layout.fillWidth: true; onEditingFinished: root.fieldText(this, "transcription.siliconflow.model") }
                            Label { text: root.t("timeout", "Timeout") }
                            SpinBox { id: siliconflowTimeoutSpin; objectName: "siliconflowTimeoutSpin"; from: 5; to: 120; value: root.value("transcription.siliconflow.timeout", 30); Layout.fillWidth: true; onValueModified: root.numberValue(siliconflowTimeoutSpin, "transcription.siliconflow.timeout") }
                            Label { text: root.t("max_retries", "Max retries") }
                            SpinBox { id: siliconflowRetriesSpin; objectName: "siliconflowRetriesSpin"; from: 0; to: 10; value: root.value("transcription.siliconflow.max_retries", 3); Layout.fillWidth: true; onValueModified: root.numberValue(siliconflowRetriesSpin, "transcription.siliconflow.max_retries") }
                        }
                    }

                    SettingsCard {
                        objectName: "qwenTranscriptionCard"
                        title: "Qwen ASR"
                        visible: root.selectedTranscriptionProvider === "qwen"
                        GridLayout {
                            columns: 2
                            rowSpacing: 12
                            columnSpacing: 12
                            Layout.fillWidth: true
                            Label { text: root.t("api_key", "API key") }
                            TextField { id: qwenApiKeyField; objectName: "qwenApiKeyField"; echoMode: TextInput.Password; text: root.value("transcription.qwen.api_key", ""); Layout.fillWidth: true; onEditingFinished: root.fieldText(qwenApiKeyField, "transcription.qwen.api_key") }
                            Label { text: root.t("base_url", "Base URL") }
                            TextField { objectName: "qwenBaseUrlField"; placeholderText: root.t("dashscope_default", "Leave empty to use DashScope default"); text: root.value("transcription.qwen.base_url", "https://dashscope.aliyuncs.com"); Layout.fillWidth: true; onEditingFinished: root.fieldText(this, "transcription.qwen.base_url") }
                            Label { text: root.t("model", "Model") }
                            TextField { objectName: "qwenModelField"; text: root.value("transcription.qwen.model", "qwen3-asr-flash"); Layout.fillWidth: true; onEditingFinished: root.fieldText(this, "transcription.qwen.model") }
                            Label { text: root.t("timeout", "Timeout") }
                            SpinBox { id: qwenTimeoutSpin; objectName: "qwenTimeoutSpin"; from: 10; to: 180; value: root.value("transcription.qwen.timeout", 30); Layout.fillWidth: true; onValueModified: root.numberValue(qwenTimeoutSpin, "transcription.qwen.timeout") }
                            Label { text: root.t("max_retries", "Max retries") }
                            SpinBox { id: qwenRetriesSpin; objectName: "qwenRetriesSpin"; from: 0; to: 10; value: root.value("transcription.qwen.max_retries", 3); Layout.fillWidth: true; onValueModified: root.numberValue(qwenRetriesSpin, "transcription.qwen.max_retries") }
                        }
                        Switch {
                            text: root.t("enable_itn", "Enable Inverse Text Normalization")
                            checked: root.value("transcription.qwen.enable_itn", true)
                            onToggled: root.setValue("transcription.qwen.enable_itn", checked)
                        }
                    }
                }
            }

            Flickable {
                objectName: "aiPage"
                contentWidth: width
                contentHeight: aiColumn.implicitHeight
                clip: true

                ColumnLayout {
                    id: aiColumn
                    width: parent.width
                    spacing: 14

                    SettingsCard {
                        title: root.t("ai_provider", "AI Provider")
                        ListModel {
                            id: aiProviderModel
                            ListElement { value: "openrouter"; label: "OpenRouter" }
                            ListElement { value: "groq"; label: "Groq" }
                            ListElement { value: "nvidia"; label: "NVIDIA" }
                            ListElement { value: "openai_compatible"; label: "OpenAI Compatible" }
                        }
                        ComboBox {
                            id: aiProviderCombo
                            objectName: "aiProviderCombo"
                            textRole: "label"
                            valueRole: "value"
                            model: aiProviderModel
                            currentIndex: root.modelValueIndex(aiProviderModel, root.selectedAiProvider)
                            Layout.fillWidth: true
                            onActivated: {
                                root.selectedAiProvider = aiProviderCombo.currentValue
                                root.setValue("ai.provider", aiProviderCombo.currentValue)
                            }
                        }
                    }

                    SettingsCard {
                        objectName: "openrouterAiCard"
                        title: "OpenRouter"
                        visible: root.selectedAiProvider === "openrouter"
                        GridLayout {
                            columns: 2
                            rowSpacing: 12
                            columnSpacing: 12
                            Layout.fillWidth: true
                            Label { text: root.t("api_key", "API key") }
                            TextField { objectName: "openrouterApiKeyField"; echoMode: TextInput.Password; text: root.value("ai.openrouter.api_key", ""); Layout.fillWidth: true; onEditingFinished: root.fieldText(this, "ai.openrouter.api_key") }
                            Label { text: root.t("model_id", "Model ID") }
                            TextField { objectName: "openrouterModelField"; text: root.value("ai.openrouter.model_id", "anthropic/claude-3-sonnet"); Layout.fillWidth: true; onEditingFinished: root.fieldText(this, "ai.openrouter.model_id") }
                        }
                    }

                    SettingsCard {
                        objectName: "groqAiCard"
                        title: "Groq"
                        visible: root.selectedAiProvider === "groq"
                        GridLayout {
                            columns: 2
                            rowSpacing: 12
                            columnSpacing: 12
                            Layout.fillWidth: true
                            Label { text: root.t("api_key", "API key") }
                            TextField { objectName: "aiGroqApiKeyField"; echoMode: TextInput.Password; text: root.value("ai.groq.api_key", ""); Layout.fillWidth: true; onEditingFinished: root.fieldText(this, "ai.groq.api_key") }
                            Label { text: root.t("model_id", "Model ID") }
                            TextField { objectName: "aiGroqModelField"; text: root.value("ai.groq.model_id", "llama-3.3-70b-versatile"); Layout.fillWidth: true; onEditingFinished: root.fieldText(this, "ai.groq.model_id") }
                        }
                    }

                    SettingsCard {
                        objectName: "nvidiaAiCard"
                        title: "NVIDIA"
                        visible: root.selectedAiProvider === "nvidia"
                        GridLayout {
                            columns: 2
                            rowSpacing: 12
                            columnSpacing: 12
                            Layout.fillWidth: true
                            Label { text: root.t("api_key", "API key") }
                            TextField { objectName: "nvidiaApiKeyField"; echoMode: TextInput.Password; text: root.value("ai.nvidia.api_key", ""); Layout.fillWidth: true; onEditingFinished: root.fieldText(this, "ai.nvidia.api_key") }
                            Label { text: root.t("model_id", "Model ID") }
                            TextField { objectName: "nvidiaModelField"; text: root.value("ai.nvidia.model_id", "nvidia/llama-3.1-nemotron-70b-instruct"); Layout.fillWidth: true; onEditingFinished: root.fieldText(this, "ai.nvidia.model_id") }
                        }
                    }

                    SettingsCard {
                        objectName: "openAiCompatibleAiCard"
                        title: root.t("openai_compatible", "OpenAI Compatible")
                        visible: root.selectedAiProvider === "openai_compatible"
                        GridLayout {
                            columns: 2
                            rowSpacing: 12
                            columnSpacing: 12
                            Layout.fillWidth: true
                            Label { text: root.t("base_url", "Base URL") }
                            TextField { id: openAiCompatibleBaseUrlField; objectName: "openAiCompatibleBaseUrlField"; text: root.value("ai.openai_compatible.base_url", ""); Layout.fillWidth: true; onEditingFinished: root.fieldText(openAiCompatibleBaseUrlField, "ai.openai_compatible.base_url") }
                            Label { text: root.t("api_key_optional", "API key (optional)") }
                            TextField { objectName: "openAiCompatibleApiKeyField"; echoMode: TextInput.Password; text: root.value("ai.openai_compatible.api_key", ""); Layout.fillWidth: true; onEditingFinished: root.fieldText(this, "ai.openai_compatible.api_key") }
                            Label { text: root.t("model_id", "Model ID") }
                            TextField { objectName: "openAiCompatibleModelField"; text: root.value("ai.openai_compatible.model_id", "local-model"); Layout.fillWidth: true; onEditingFinished: root.fieldText(this, "ai.openai_compatible.model_id") }
                        }
                    }

                    SettingsCard {
                        title: root.t("ai_behavior", "AI Behavior")
                        Switch { text: root.t("enable_ai_optimization", "Enable AI text optimization"); checked: root.value("ai.enabled", false); onToggled: root.setValue("ai.enabled", checked) }
                        Switch { text: root.t("filter_thinking_tags", "Filter thinking tags"); checked: root.value("ai.filter_thinking", true); onToggled: root.setValue("ai.filter_thinking", checked) }
                        Switch { text: root.t("enable_sentence_split", "Enable sentence split"); checked: root.value("ai.sentence_split.enabled", false); onToggled: root.setValue("ai.sentence_split.enabled", checked) }
                        Switch { text: root.t("start_ai_after_first_chunk", "Start AI after first ASR chunk"); checked: root.value("ai.first_chunk_output.enabled", false); onToggled: root.setValue("ai.first_chunk_output.enabled", checked) }
                        Switch { text: root.t("enable_ai_streaming_output", "Enable AI streaming output"); checked: root.value("ai.streaming_enabled", false); onToggled: root.setValue("ai.streaming_enabled", checked) }
                        GridLayout {
                            columns: 2
                            rowSpacing: 12
                            columnSpacing: 12
                            Layout.fillWidth: true
                            Label { text: root.t("timeout", "Timeout") }
                            SpinBox { id: aiTimeoutSpin; objectName: "aiTimeoutSpin"; from: 5; to: 120; value: root.value("ai.timeout", 30); Layout.fillWidth: true; onValueModified: root.numberValue(aiTimeoutSpin, "ai.timeout") }
                            Label { text: root.t("max_retries", "Max retries") }
                            SpinBox { id: aiRetriesSpin; objectName: "aiRetriesSpin"; from: 0; to: 5; value: root.value("ai.retries", 3); Layout.fillWidth: true; onValueModified: root.numberValue(aiRetriesSpin, "ai.retries") }
                        }
                    }

                    SettingsCard {
                        title: root.t("system_prompt", "System Prompt")
                        Label {
                            text: root.t("system_prompt_help", "Define the AI assistant role. Transcribed speech is sent as the user message.")
                            color: palette.text
                            opacity: 0.72
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }
                        ScrollView {
                            objectName: "aiPromptScrollView"
                            Layout.fillWidth: true
                            Layout.preferredHeight: 170
                            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                            ScrollBar.vertical.policy: ScrollBar.AsNeeded

                            TextArea {
                                id: aiPromptField
                                objectName: "aiPromptField"
                                placeholderText: root.t("system_prompt_placeholder", "You are a professional transcription refinement specialist. Output only the corrected text.")
                                text: root.value("ai.prompt", "")
                                width: parent.width
                                wrapMode: TextEdit.WordWrap
                                verticalAlignment: TextEdit.AlignTop
                                selectByMouse: true
                                onEditingFinished: root.fieldText(aiPromptField, "ai.prompt")
                            }
                        }
                    }
                }
            }

            Flickable {
                objectName: "audioInputPage"
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
                        Label { text: root.t("chunk_duration", "Chunk duration") + ": " + chunkDurationSlider.value.toFixed(1) + " " + root.t("seconds", "seconds") }
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
                            Label { text: root.t("clipboard_restore_delay_ms", "Clipboard restore delay (ms)") }
                            SpinBox { id: clipboardDelaySpin; objectName: "clipboardDelaySpin"; from: 0; to: 10000; value: Math.round(root.value("input.clipboard_restore_delay", 0.5) * 1000); Layout.fillWidth: true; onValueModified: root.setValue("input.clipboard_restore_delay", clipboardDelaySpin.value / 1000.0) }
                            Label { text: root.t("typing_delay_ms", "Typing delay (ms)") }
                            SpinBox { id: typingDelaySpin; objectName: "typingDelaySpin"; from: 0; to: 1000; value: Math.round(root.value("input.typing_delay", 0.01) * 1000); Layout.fillWidth: true; onValueModified: root.setValue("input.typing_delay", typingDelaySpin.value / 1000.0) }
                        }
                        Switch { text: root.t("enable_fallback", "Enable fallback to alternative method"); checked: root.value("input.fallback_enabled", true); onToggled: root.setValue("input.fallback_enabled", checked) }
                        Switch { text: root.t("auto_detect_terminal", "Auto-detect terminal applications"); checked: root.value("input.auto_detect_terminal", true); onToggled: root.setValue("input.auto_detect_terminal", checked) }
                    }
                }
            }

            Item {
                objectName: "historyPage"
                Layout.fillWidth: true
                Layout.fillHeight: true

                ColumnLayout {
                    id: historyColumn
                    anchors.fill: parent
                    spacing: 14

                    SettingsCard {
                        title: root.t("history", "History")
                        fillBody: true
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Timer {
                            id: historySearchDebounce
                            interval: 250
                            repeat: false
                            onTriggered: root.viewModel && root.viewModel.refreshHistory(historySearchField.text)
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8
                            TextField {
                                id: historySearchField
                                objectName: "historySearchField"
                                placeholderText: root.t("search_history", "Search in transcription or AI text")
                                Layout.fillWidth: true
                                Layout.minimumWidth: 220
                                onTextChanged: historySearchDebounce.restart()
                                onAccepted: root.viewModel && root.viewModel.refreshHistory(text)
                            }
                            Button {
                                objectName: "historyRefreshButton"
                                text: root.t("refresh", "Refresh")
                                Layout.preferredWidth: 96
                                onClicked: root.viewModel && root.viewModel.refreshHistory(historySearchField.text)
                            }
                            Button {
                                objectName: "historyBatchReprocessButton"
                                text: root.t("batch_reprocess", "Batch Reprocess")
                                Layout.preferredWidth: 148
                                onClicked: root.viewModel && root.viewModel.startBatchReprocess()
                            }
                        }

                        Rectangle {
                            objectName: "historyListFrame"
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            Layout.minimumHeight: 280
                            radius: 8
                            color: palette.base
                            border.color: palette.mid
                            border.width: 1
                            clip: true

                            Label {
                                id: historyEmptyState
                                objectName: "historyEmptyState"
                                anchors.centerIn: parent
                                text: root.t("no_history_records_loaded", "No history records loaded")
                                opacity: 0.62
                                visible: historyList.count === 0
                            }

                            ListView {
                                id: historyList
                                objectName: "historyList"
                                anchors.fill: parent
                                anchors.margins: 8
                                spacing: 6
                                clip: true
                                model: root.viewModel ? root.viewModel.historyRecords : []
                                property int delegateTextMinimumWidth: 260
                                property int delegateStatusWidth: 74
                                property int delegateActionWidth: 76
                                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                                onMovementEnded: {
                                    if (atYEnd && root.viewModel) {
                                        root.viewModel.loadMoreHistory()
                                    }
                                }

                                delegate: Rectangle {
                                    width: ListView.view.width
                                    height: 82
                                    radius: 8
                                    color: palette.window
                                    border.color: palette.mid
                                    border.width: 1

                                    MouseArea {
                                        anchors.fill: parent
                                        acceptedButtons: Qt.LeftButton
                                        onDoubleClicked: root.viewModel && root.viewModel.openHistoryDetail(index)
                                    }

                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.margins: 10
                                        spacing: 8

                                        ColumnLayout {
                                            Layout.preferredWidth: 88
                                            Layout.minimumWidth: 76
                                            Layout.maximumWidth: 96
                                            Layout.fillHeight: true
                                            spacing: 3
                                            Label {
                                                text: modelData.displayTime
                                                font.pixelSize: 12
                                                font.weight: Font.Medium
                                                elide: Text.ElideRight
                                                Layout.fillWidth: true
                                            }
                                            Label {
                                                text: modelData.durationText
                                                opacity: 0.7
                                                font.pixelSize: 12
                                                Layout.fillWidth: true
                                            }
                                        }

                                        ColumnLayout {
                                            objectName: "historyDelegateTextColumn"
                                            Layout.fillWidth: true
                                            Layout.minimumWidth: historyList.delegateTextMinimumWidth
                                            Layout.fillHeight: true
                                            spacing: 4
                                            Label {
                                                text: modelData.primaryText
                                                font.pixelSize: 13
                                                font.weight: Font.Medium
                                                elide: Text.ElideRight
                                                Layout.fillWidth: true
                                            }
                                            Label {
                                                text: modelData.transcriptionText
                                                opacity: 0.68
                                                font.pixelSize: 12
                                                elide: Text.ElideRight
                                                Layout.fillWidth: true
                                            }
                                            Label {
                                                text: modelData.fullTime
                                                opacity: 0.52
                                                font.pixelSize: 11
                                                elide: Text.ElideRight
                                                Layout.fillWidth: true
                                            }
                                        }

                                        Label {
                                            objectName: "historyDelegateStatusLabel"
                                            text: modelData.statusText
                                            horizontalAlignment: Text.AlignHCenter
                                            verticalAlignment: Text.AlignVCenter
                                            font.pixelSize: 12
                                            elide: Text.ElideRight
                                            Layout.preferredWidth: historyList.delegateStatusWidth
                                            Layout.minimumWidth: 68
                                            Layout.maximumWidth: 82
                                        }

                                        Button {
                                            objectName: "historyDetailButton"
                                            text: root.t("detail", "Detail")
                                            Layout.preferredWidth: historyList.delegateActionWidth
                                            Layout.minimumWidth: 72
                                            onClicked: root.viewModel && root.viewModel.openHistoryDetail(index)
                                        }
                                    }
                                }
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            Label {
                                objectName: "historyTotalLabel"
                                text: root.viewModel ? root.viewModel.historyTotalText : root.t("total_records_zero", "Total Records: 0")
                                elide: Text.ElideRight
                                Layout.preferredWidth: 150
                            }
                            Label {
                                objectName: "historyDurationLabel"
                                text: root.viewModel ? root.viewModel.historyDurationText : root.t("total_duration_zero", "Total Duration: 0.0s")
                                elide: Text.ElideRight
                                Layout.preferredWidth: 190
                            }
                            Label {
                                objectName: "historySuccessRateLabel"
                                text: root.viewModel ? root.viewModel.historySuccessRateText : root.t("success_rate_zero", "Success Rate: 0%")
                                elide: Text.ElideRight
                                Layout.preferredWidth: 160
                            }
                            Item { Layout.fillWidth: true }
                        }
                    }
                }
            }
        }
    }

    Dialog {
        id: historyDetailPanel
        objectName: "historyDetailPanel"
        modal: true
        visible: root.viewModel ? root.viewModel.historyDetailVisible : false
        title: root.t("recording_details", "Recording Details")
        anchors.centerIn: parent
        width: Math.min(root.width - 48, 860)
        height: Math.min(root.height - 64, 680)
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        onClosed: {
            if (root.viewModel && root.viewModel.historyDetailVisible) {
                root.viewModel.closeHistoryDetail()
            }
        }

        footer: DialogButtonBox {
            Button {
                objectName: "historyDetailCopyButton"
                text: root.t("copy_to_clipboard", "Copy")
                DialogButtonBox.buttonRole: DialogButtonBox.ActionRole
                onClicked: root.viewModel && root.viewModel.copySelectedHistoryText()
            }
            Button {
                objectName: "historyDetailRetryButton"
                text: root.t("retry", "Retry")
                DialogButtonBox.buttonRole: DialogButtonBox.ActionRole
                onClicked: root.viewModel && root.viewModel.retrySelectedHistoryRecord()
            }
            Button {
                objectName: "historyDetailDeleteButton"
                text: root.t("delete_record", "Delete")
                DialogButtonBox.buttonRole: DialogButtonBox.DestructiveRole
                onClicked: root.viewModel && root.viewModel.deleteSelectedHistoryRecord()
            }
            Button {
                objectName: "historyDetailCloseButton"
                text: root.t("close", "Close")
                DialogButtonBox.buttonRole: DialogButtonBox.AcceptRole
                onClicked: root.viewModel && root.viewModel.closeHistoryDetail()
            }
        }

        contentItem: ScrollView {
            objectName: "historyDetailScrollView"
            clip: true
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            ScrollBar.vertical.policy: ScrollBar.AsNeeded

            ColumnLayout {
                width: historyDetailPanel.availableWidth
                spacing: 12

                Frame {
                    Layout.fillWidth: true
                    padding: 14
                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 8
                        Label {
                            text: root.historyDetailValue("primaryText", "")
                            font.pixelSize: 15
                            font.weight: Font.Medium
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }
                        GridLayout {
                            columns: 2
                            rowSpacing: 6
                            columnSpacing: 14
                            Layout.fillWidth: true
                            Label { text: root.t("time", "Time"); opacity: 0.65 }
                            Label { text: root.historyDetailValue("fullTime", ""); elide: Text.ElideRight; Layout.fillWidth: true }
                            Label { text: root.t("duration", "Duration"); opacity: 0.65 }
                            Label { text: root.historyDetailValue("durationText", ""); elide: Text.ElideRight; Layout.fillWidth: true }
                            Label { text: root.t("audio_file", "Audio File"); opacity: 0.65 }
                            Label { text: root.historyDetailValue("audioPath", ""); elide: Text.ElideMiddle; Layout.fillWidth: true }
                            Label { text: root.t("reprocess_of", "Reprocess Of"); opacity: 0.65 }
                            Label { text: root.historyDetailValue("reprocessParentId", ""); elide: Text.ElideRight; Layout.fillWidth: true }
                        }
                    }
                }

                Frame {
                    objectName: "historyDetailDiagnosticsCard"
                    Layout.fillWidth: true
                    padding: 14
                    GridLayout {
                        anchors.fill: parent
                        columns: 4
                        rowSpacing: 8
                        columnSpacing: 14
                        Label { text: root.t("diagnostics", "Diagnostics"); opacity: 0.65 }
                        Label { text: root.historyDetailValue("diagnosticsText", ""); elide: Text.ElideRight; Layout.fillWidth: true }
                        Label { text: root.t("mode", "Mode"); opacity: 0.65 }
                        Label { text: root.historyDetailValue("streamingMode", ""); elide: Text.ElideRight; Layout.fillWidth: true }
                        Label { text: root.t("provider", "Provider"); opacity: 0.65 }
                        Label { text: root.historyDetailValue("transcriptionProvider", ""); elide: Text.ElideRight; Layout.fillWidth: true }
                        Label { text: root.t("transcribe_time", "Transcribe Time"); opacity: 0.65 }
                        Label { text: root.historyDetailValue("transcribeTime", ""); elide: Text.ElideRight; Layout.fillWidth: true }
                        Label { text: root.t("fallback", "Fallback"); opacity: 0.65 }
                        Label { text: root.historyDetailValue("fallbackUsed", ""); elide: Text.ElideRight; Layout.fillWidth: true }
                        Label { text: root.t("fallback_reason", "Fallback Reason"); opacity: 0.65 }
                        Label { text: root.historyDetailValue("fallbackReason", ""); elide: Text.ElideRight; Layout.fillWidth: true }
                    }
                }

                Frame {
                    Layout.fillWidth: true
                    padding: 14
                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 8
                        Label {
                            text: root.t("transcription", "Transcription")
                            font.pixelSize: 14
                            font.weight: Font.Medium
                        }
                        TextArea {
                            objectName: "historyDetailTranscriptionText"
                            text: root.historyDetailValue("transcriptionText", "")
                            readOnly: true
                            wrapMode: TextEdit.WordWrap
                            Layout.fillWidth: true
                            Layout.preferredHeight: 150
                        }
                    }
                }

                Frame {
                    Layout.fillWidth: true
                    padding: 14
                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 8
                        Label {
                            text: root.t("final_text", "Final Text")
                            font.pixelSize: 14
                            font.weight: Font.Medium
                        }
                        TextArea {
                            objectName: "historyDetailFinalText"
                            text: root.historyDetailValue("primaryText", "")
                            readOnly: true
                            wrapMode: TextEdit.WordWrap
                            Layout.fillWidth: true
                            Layout.preferredHeight: 170
                        }
                    }
                }
            }
        }
    }
}
