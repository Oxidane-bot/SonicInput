import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: root
    objectName: "fluentAboutWindow"
    title: "About SonicInput"
    width: 560
    height: 540
    minimumWidth: 520
    minimumHeight: 520
    visible: false
    color: palette.window
    font.family: "Microsoft YaHei UI"

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 28
        spacing: 16

        RowLayout {
            Layout.fillWidth: true
            spacing: 16

            Rectangle {
                Layout.preferredWidth: 54
                Layout.preferredHeight: 54
                radius: 14
                color: palette.highlight

                Label {
                    anchors.centerIn: parent
                    text: "S"
                    color: palette.highlightedText
                    font.pixelSize: 26
                    font.weight: Font.DemiBold
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 4

                Label {
                    text: "SonicInput"
                    font.pixelSize: 26
                    font.weight: Font.DemiBold
                    Layout.fillWidth: true
                }

                Label {
                    id: aboutVersionLabel
                    objectName: "aboutVersionLabel"
                    text: "Version " + appVersion
                    opacity: 0.72
                    font.pixelSize: 13
                    Layout.fillWidth: true
                }
            }
        }

        Label {
            text: "AI-powered voice input for Windows, built for fast transcription, optional text refinement, and low-friction keyboard-driven capture."
            wrapMode: Text.WordWrap
            opacity: 0.78
            lineHeight: 1.18
            Layout.fillWidth: true
        }

        Frame {
            Layout.fillWidth: true
            padding: 18

            ColumnLayout {
                anchors.fill: parent
                spacing: 12

                Label {
                    text: "Core Capabilities"
                    font.pixelSize: 16
                    font.weight: Font.DemiBold
                }

                ColumnLayout {
                    id: aboutFeatureList
                    objectName: "aboutFeatureList"
                    Layout.fillWidth: true
                    spacing: 8

                    Label { text: "Local sherpa-onnx speech recognition"; opacity: 0.86 }
                    Label { text: "Cloud ASR providers for fallback and specialist models"; opacity: 0.86 }
                    Label { text: "AI text optimization with multiple LLM providers"; opacity: 0.86 }
                    Label { text: "Global hotkeys and Windows text input integration"; opacity: 0.86 }
                }
            }
        }

        Frame {
            Layout.fillWidth: true
            padding: 18

            ColumnLayout {
                anchors.fill: parent
                spacing: 12

                Label {
                    text: "Quick Controls"
                    font.pixelSize: 16
                    font.weight: Font.DemiBold
                }

                GridLayout {
                    id: aboutHotkeyList
                    objectName: "aboutHotkeyList"
                    columns: 2
                    rowSpacing: 8
                    columnSpacing: 18
                    Layout.fillWidth: true

                    Label { text: "Configured hotkey"; opacity: 0.72 }
                    Label { text: "Toggle recording"; Layout.fillWidth: true }
                    Label { text: "Double-click tray icon"; opacity: 0.72 }
                    Label { text: "Open settings"; Layout.fillWidth: true }
                    Label { text: "Middle-click tray icon"; opacity: 0.72 }
                    Label { text: "Toggle recording"; Layout.fillWidth: true }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true

            Label {
                text: "SonicInput Team"
                opacity: 0.62
                Layout.fillWidth: true
            }

            Button {
                objectName: "aboutCloseButton"
                text: "Close"
                onClicked: root.close()
            }
        }
    }
}
