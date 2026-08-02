#Requires AutoHotkey v2.0
#SingleInstance Force
#MaxThreadsPerHotkey 2

SendMode("Input")
SetKeyDelay(-1, -1)
SetControlDelay(-1)

global Toggle := false
global TargetWindowTitle := "ahk_exe cod.exe"
global TargetWindowId := 0
global MarkerFilePath := ""
global HoldLMBTime := 65
global PostLMBWait := 100
global PostRMBWait := 100
global PreMeleeWait := 100
global ScoreboardToggling := 1
global Movement := 0
global HoldWTime := 400
global WSWaitTime := 5000
global LastWSTime := 0
global MovementBusy := false
global MovementActive := false
global VWaitTime := 530
global BackgroundInput := 0
global MouseBlocker := 0
global AutoStart := 0
global BlockOverlayBlocker := 0
global ToggleKey := "8"
global ExitKey := "F2"
global ScoreboardKey := "sc029"
global MeleeKey := "v"

ApplyOverrides()
ConfigureHotkeys()
WriteMarker("READY")
if AutoStart {
    ToggleScript()
}

ApplyOverrides() {
    global TargetWindowTitle, MarkerFilePath, HoldLMBTime, PostLMBWait, PostRMBWait, PreMeleeWait, VWaitTime, ScoreboardToggling, Movement, HoldWTime, BackgroundInput, MouseBlocker, AutoStart, ToggleKey, ExitKey, ScoreboardKey, MeleeKey

    TargetWindowTitle := ReadStringArg("--target-title", TargetWindowTitle)
    MarkerFilePath := ReadStringArg("--marker-file", MarkerFilePath)
    HoldLMBTime := ReadIntArg("--hold-lmb-time", HoldLMBTime)
    PostLMBWait := ReadIntArg("--post-lmb-wait", PostLMBWait)
    PostRMBWait := ReadIntArg("--post-rmb-wait", PostRMBWait)
    PreMeleeWait := ReadIntArg("--pre-melee-wait", PreMeleeWait)
    VWaitTime := ReadIntArg("--v-wait-time", VWaitTime)
    ScoreboardToggling := ReadIntArg("--scoreboard-toggling", ScoreboardToggling)
    Movement := ReadIntArg("--movement", Movement)
    HoldWTime := ReadIntArg("--hold-w-time", HoldWTime)
    BackgroundInput := ReadIntArg("--background-input", BackgroundInput)
    MouseBlocker := ReadIntArg("--block-input", MouseBlocker)
    AutoStart := ReadIntArg("--auto-start", AutoStart)
    ToggleKey := NormalizeKeyName(ReadStringArg("--toggle-key", ToggleKey))
    ExitKey := NormalizeKeyName(ReadStringArg("--exit-key", ExitKey))
    ScoreboardKey := NormalizeKeyName(ReadStringArg("--scoreboard-key", ScoreboardKey))
    MeleeKey := NormalizeKeyName(ReadStringArg("--melee-key", MeleeKey))
}

ConfigureHotkeys() {
    global TargetWindowTitle, BackgroundInput, ToggleKey, ExitKey

    if BackgroundInput {
        Hotkey(ExitKey, ExitScript)
        return
    }

    HotIfWinActive(TargetWindowTitle)
    Hotkey(ToggleKey, ToggleScript)
    Hotkey(ExitKey, ExitScript)
    HotIf()
}

ReadIntArg(flag, fallback) {
    loop A_Args.Length {
        if (A_Args[A_Index] = flag) && (A_Index < A_Args.Length) {
            value := Integer(A_Args[A_Index + 1])
            return value >= 0 ? value : fallback
        }
    }
    return fallback
}

ReadStringArg(flag, fallback) {
    loop A_Args.Length {
        if (A_Args[A_Index] = flag) && (A_Index < A_Args.Length) {
            value := Trim(A_Args[A_Index + 1])
            return value != "" ? value : fallback
        }
    }
    return fallback
}

NormalizeKeyName(value) {
    cleaned := Trim(value, " `t`r`n{}()")
    if cleaned = "" {
        return value
    }
    if RegExMatch(cleaned, "i)^(sc|vk)[0-9a-f]+$") {
        return StrLower(cleaned)
    }
    return cleaned
}

FormatSendKey(value) {
    return StrLen(value) = 1 ? value : "{" value "}"
}

SendKey(value) {
    global BackgroundInput
    key := FormatSendKey(value)
    if BackgroundInput {
        target := ResolveTargetWindow()
        if target = "" {
            return
        }
        if WinActive(target) {
            Send(key)
            return
        }
        try {
            ControlSend(key, , target)
            return
        } catch {
            return
        }
    }
    Send(key)
}

SendMouse(button, state) {
    global BackgroundInput
    if BackgroundInput {
        target := ResolveTargetWindow()
        if target = "" {
            return
        }
        whichButton := button = "LButton" ? "Left" : button = "RButton" ? "Right" : button
        if state != "down" {
            return
        }
        try {
            ControlClick(BackgroundClickPoint(target), target, "", whichButton, 1, "NA Pos")
            return
        } catch {
            return
        }
    }
    Send("{" button " " state "}")
}

HoldMouse(button, duration) {
    global BackgroundInput
    if BackgroundInput {
        target := ResolveTargetWindow()
        if target = "" {
            return
        }
        whichButton := button = "LButton" ? "Left" : button = "RButton" ? "Right" : button
        clickPoint := BackgroundClickPoint(target)
        downSent := false
        try {
            ControlClick(clickPoint, target, "", whichButton, 1, "D NA Pos")
            downSent := true
            Sleep(duration)
        } catch {
        } finally {
            if downSent {
                try ControlClick(clickPoint, target, "", whichButton, 1, "U NA Pos")
            }
        }
        return
    }
    Send("{" button " down}")
    Sleep(duration)
    Send("{" button " up}")
}

BackgroundClickPoint(target) {
    try {
        WinGetClientPos(&cx, &cy, &cw, &ch, target)
        return "x" Max(1, Floor(cw / 2)) " y" Max(1, Floor(ch / 2))
    } catch {
        return "x1 y1"
    }
}

UsingBackgroundInput() {
    global BackgroundInput
    return BackgroundInput && ResolveTargetWindow() != ""
}

ResolveTargetWindow() {
    global TargetWindowTitle, TargetWindowId
    if TargetWindowId && WinExist("ahk_id " TargetWindowId) {
        return "ahk_id " TargetWindowId
    }
    hwnd := WinExist(TargetWindowTitle)
    if hwnd {
        TargetWindowId := hwnd
        return "ahk_id " hwnd
    }
    return ""
}

UpdateBackgroundOverlay(active) {
    global BackgroundInput, MouseBlocker
    if !BackgroundInput {
        return
    }
    if active {
        label := MouseBlocker ? "[AFK] Script Active  |  Inputs Blocked" : "[AFK] Script Active"
        target := ResolveTargetWindow()
        if target != "" {
            WinGetPos(&wx, &wy, &ww, &wh, target)
            ToolTip(label, wx + 10, wy + 40, 3)
        } else {
            ToolTip(label, 10, 40, 3)
        }
    } else {
        ToolTip(, , , 3)
    }
}

WriteMarker(event) {
    global MarkerFilePath
    if MarkerFilePath = "" {
        return
    }
    try FileAppend(event . "`n", MarkerFilePath, "UTF-8")
}

CreateBlockOverlay() {
    global BackgroundInput, MouseBlocker, BlockOverlayBlocker
    if !BackgroundInput || !MouseBlocker
        return
    target := ResolveTargetWindow()
    if target = ""
        return
    DestroyBlockOverlay()
    WinGetPos(&wx, &wy, &ww, &wh, target)
    blocker := Gui("+AlwaysOnTop -Caption +ToolWindow +E0x80000 +E0x8000000")
    blocker.BackColor := "000000"
    blocker.Show("x" wx " y" wy " w" ww " h" wh " NoActivate")
    WinSetTransparent(1, "ahk_id " blocker.Hwnd)
    BlockOverlayBlocker := blocker
}

DestroyBlockOverlay() {
    global BlockOverlayBlocker
    if BlockOverlayBlocker {
        BlockOverlayBlocker.Destroy()
        BlockOverlayBlocker := 0
    }
}

StartMovement() {
    global Movement, Toggle, LastWSTime, MovementActive
    if !Movement || !Toggle || MovementActive
        return
    MovementActive := true
    LastWSTime := A_TickCount
    SendKey("s down")
    SetTimer(MovementLoop, 50)
}

StopMovement() {
    global LastWSTime, MovementActive
    SetTimer(MovementLoop, 0)
    if !MovementActive
        return
    MovementActive := false
    SendKey("w up")
    SendKey("s up")
    LastWSTime := 0
}

MovementLoop() {
    global Movement, Toggle, LastWSTime, HoldWTime, WSWaitTime, MovementBusy
    if !Toggle || !Movement {
        StopMovement()
        return
    }
    if MovementBusy || A_TickCount - LastWSTime < WSWaitTime
        return
    MovementBusy := true
    try {
        SendKey("s up")
        SendKey("w down")
        Sleep(HoldWTime)
        SendKey("w up")
        if Toggle && Movement
            SendKey("s down")
        LastWSTime := A_TickCount
    } finally {
        MovementBusy := false
    }
}

ToggleScript(*) {
    global Toggle, BackgroundInput

    Toggle := !Toggle
    if Toggle {
        if BackgroundInput && ResolveTargetWindow() = "" {
            MouseGetPos(&mx, &my)
            ToolTip("Game window not found - inputs may not work", mx + 18, my + 22, 4)
            SetTimer(() => ToolTip(,,, 4), -3000)
        }
        WriteMarker("START")
        ShowStatus("ON")
        UpdateBackgroundOverlay(true)
        CreateBlockOverlay()
        StartMovement()
        SetTimer(MainLoop, -1)
    } else {
        WriteMarker("END")
        ShowStatus("OFF")
        UpdateBackgroundOverlay(false)
        StopMovement()
        DestroyBlockOverlay()
    }
}

ExitScript(*) {
    global BackgroundInput

    WriteMarker("EXIT")
    StopMovement()
    UpdateBackgroundOverlay(false)
    DestroyBlockOverlay()
    ExitApp()
}

ShowStatus(state) {
    target := ResolveTargetWindow()
    if target != "" {
        WinGetPos(&wx, &wy, &ww, &wh, target)
        ToolTip("SCRIPT " state, wx + 18, wy + 18, 1)
    } else {
        MouseGetPos(&mx, &my)
        ToolTip("SCRIPT " state, mx + 18, my + 22, 1)
    }
    SetTimer(ClearCursorPopup, -900)
}

ClearCursorPopup() {
    ToolTip(, , , 1)
    ToolTip(, , , 2)
}

MainLoop() {
    global Toggle, HoldLMBTime, PostLMBWait, PostRMBWait, PreMeleeWait, VWaitTime, ScoreboardToggling, ScoreboardKey, MeleeKey

    loop {
        if !Toggle {
            break
        }

        if UsingBackgroundInput() {
            HoldMouse("LButton", HoldLMBTime)
            if ScoreboardToggling {
                Sleep(10)
                SendKey(ScoreboardKey)
            }
        } else {
            SendMouse("LButton", "down")
            if ScoreboardToggling {
                Sleep(10)
                SendKey(ScoreboardKey)
            }
            Sleep(HoldLMBTime)
            SendMouse("LButton", "up")
        }

        Sleep(PostLMBWait)
        SendMouse("RButton", "down")
        SendMouse("RButton", "up")

        Sleep(PostRMBWait)
        if ScoreboardToggling {
            Sleep(10)
            SendKey(ScoreboardKey)
        }
        Sleep(PreMeleeWait)
        SendKey(MeleeKey)
        Sleep(VWaitTime)
    }
}
