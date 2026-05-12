import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Frame {
    id: card
    Layout.fillWidth: true
    padding: 18
    font.family: "Microsoft YaHei UI"

    property string title: ""
    property bool fillBody: false
    default property alias content: body.data

    ColumnLayout {
        anchors.fill: parent
        spacing: 12

        Label {
            text: card.title
            font.family: "Microsoft YaHei UI"
            font.pixelSize: 16
            font.weight: Font.Medium
            Layout.fillWidth: true
        }

        ColumnLayout {
            id: body
            Layout.fillWidth: true
            Layout.fillHeight: card.fillBody
            spacing: 10
        }
    }
}
