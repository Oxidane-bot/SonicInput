import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Flickable {
    id: page
    contentWidth: width
    contentHeight: column.implicitHeight
    clip: true

    property string title: ""
    property string body: ""
    property string note: ""

    ColumnLayout {
        id: column
        width: page.width
        spacing: 14

        SettingsCard {
            title: page.title
            Label {
                text: page.body
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            Label {
                text: page.note
                opacity: 0.72
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
        }
    }
}
