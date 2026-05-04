import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Window {
    id: root
    objectName: "fluentRecordingOverlay"
    width: 252
    height: 52
    visible: viewModel ? viewModel.visible : false
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
    color: "transparent"
    property var viewModel: overlayViewModel
    property int dragStartX: 0
    property int dragStartY: 0

    function visualLevel(index) {
        var raw = root.viewModel ? Math.max(0, Math.min(1, root.viewModel.audioLevel)) : 0
        var boosted = Math.pow(raw, 0.72)
        var center = Math.abs(index - 5)
        var falloff = Math.max(0.26, 1.0 - center * 0.095)
        var motion = 0.045 * Math.sin((Date.now() / 120) + index * 0.9)
        return Math.max(0.08, Math.min(1.0, boosted * falloff + motion))
    }

    Rectangle {
        id: hud
        anchors.fill: parent
        radius: 17
        color: "#e51b2029"
        border.color: "#40556b83"
        border.width: 1
        property color accentColor: stateColor

        property color stateColor: {
            if (!root.viewModel) return "#8a94a6"
            if (root.viewModel.state === "recording") return "#62c4ff"
            if (root.viewModel.state === "completed") return "#62d084"
            if (root.viewModel.state === "warning") return "#d8ad54"
            if (root.viewModel.state === "error") return "#ea6a6a"
            return "#8a94a6"
        }

        MouseArea {
            id: dragArea
            anchors.fill: parent
            acceptedButtons: Qt.LeftButton
            onPressed: function(mouse) {
                root.dragStartX = mouse.x
                root.dragStartY = mouse.y
            }
            onPositionChanged: function(mouse) {
                if (pressed) {
                    root.x += mouse.x - root.dragStartX
                    root.y += mouse.y - root.dragStartY
                }
            }
            onReleased: {
                if (overlayHost) {
                    overlayHost.save_position(root.x, root.y)
                }
            }
        }

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 8
            anchors.rightMargin: 8
            spacing: 4

            RowLayout {
                Layout.preferredWidth: 54
                Layout.alignment: Qt.AlignVCenter
                spacing: 5

                Rectangle {
                    width: 8
                    height: 8
                    radius: 4
                    color: hud.accentColor
                    opacity: root.viewModel && root.viewModel.state === "recording" ? 1.0 : 0.78
                }

                Label {
                    text: root.viewModel ? root.viewModel.elapsedText : "00:00"
                    font.pixelSize: 12
                    font.weight: Font.Medium
                    color: "#e7edf6"
                }
            }

            Item {
                id: waveformMeter
                objectName: "waveformMeter"
                Layout.fillWidth: true
                Layout.preferredHeight: 40
                Layout.alignment: Qt.AlignVCenter

                Row {
                    anchors.centerIn: parent
                    spacing: 3

                    Repeater {
                        model: 11
                        Rectangle {
                            width: 6
                            height: 6 + root.visualLevel(index) * 28
                            radius: 3
                            anchors.verticalCenter: parent.verticalCenter
                            color: index === 5 ? "#d9f3ff" : hud.accentColor
                            opacity: 0.28 + root.visualLevel(index) * 0.58

                            Behavior on height {
                                NumberAnimation { duration: 90; easing.type: Easing.OutCubic }
                            }
                            Behavior on opacity {
                                NumberAnimation { duration: 90; easing.type: Easing.OutCubic }
                            }
                        }
                    }
                }
            }

            Item {
                id: stopSlot
                Layout.preferredWidth: 54
                Layout.fillHeight: true
                Layout.alignment: Qt.AlignVCenter

                Item {
                    id: stopButton
                    width: 28
                    height: 28
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    property bool hovered: stopMouse.containsMouse

                    Rectangle {
                        anchors.fill: parent
                        radius: 8
                        color: stopButton.hovered ? "#263244" : "transparent"
                        border.color: stopButton.hovered ? "#6f839a" : "#405267"
                        border.width: 1
                        opacity: stopButton.hovered ? 0.9 : 0.42
                    }

                    Rectangle {
                        width: 7
                        height: 7
                        radius: 2
                        anchors.centerIn: parent
                        color: stopButton.hovered ? "#eef4fb" : "#b8c5d3"
                    }

                    MouseArea {
                        id: stopMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        onClicked: {
                            if (root.viewModel) {
                                root.viewModel.requestStop()
                            }
                        }
                    }

                    ToolTip.text: "Stop Recording"
                    ToolTip.visible: hovered
                    ToolTip.delay: 500
                    ToolTip.timeout: 3000
                }
            }
        }
    }
}
