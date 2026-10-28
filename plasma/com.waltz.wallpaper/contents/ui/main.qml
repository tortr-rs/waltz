// the video waltz picked, looped and muted, cropped to fill the screen.
// waltz sets Video through plasmashell's scripting, so it changes without a restart
import QtQuick
import QtMultimedia
import org.kde.plasma.plasmoid

WallpaperItem {
    id: root

    Rectangle {
        anchors.fill: parent
        color: "black"
    }

    VideoOutput {
        id: out
        anchors.fill: parent
        fillMode: VideoOutput.PreserveAspectCrop
    }

    MediaPlayer {
        id: player
        source: root.configuration.Video
        loops: MediaPlayer.Infinite
        videoOutput: out
        onSourceChanged: play()
        Component.onCompleted: play()
    }
}
