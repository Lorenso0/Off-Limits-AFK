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
global PreMeleeWait := 100
global VWaitTime := 550
global ReticleMode := 0
global AdsWait := 250
global ScoreboardToggling := 1
global BackgroundInput := 0
global ToggleKey := "8"
global ExitKey := "F2"
global ScoreboardKey := "sc029"
global MeleeKey := "v"

ApplyOverrides()
ConfigureHotkeys()
WriteMarker("READY")

ApplyOverrides() {
    global TargetWindowTitle, MarkerFilePath, HoldLMBTime, PreMeleeWait, VWaitTime, ReticleMode, AdsWait, ScoreboardToggling, BackgroundInput, ToggleKey, ExitKey, ScoreboardKey, MeleeKey

    TargetWindowTitle := ReadStringArg("--target-title", TargetWindowTitle)
    MarkerFilePath := ReadStringArg("--marker-file", MarkerFilePath)
    HoldLMBTime := ReadIntArg("--hold-lmb-time", HoldLMBTime)
    PreMeleeWait := ReadIntArg("--pre-melee-wait", PreMeleeWait)
    VWaitTime := ReadIntArg("--v-wait-time", VWaitTime)
    ReticleMode := ReadIntArg("--reticle-mode", ReticleMode)
    AdsWait := ReadIntArg("--ads-wait", AdsWait)
    ScoreboardToggling := ReadIntArg("--scoreboard-toggling", ScoreboardToggling)
    BackgroundInput := ReadIntArg("--background-input", BackgroundInput)
    ToggleKey := NormalizeKeyName(ReadStringArg("--toggle-key", ToggleKey))
    ExitKey := NormalizeKeyName(ReadStringArg("--exit-key", ExitKey))
    ScoreboardKey := NormalizeKeyName(ReadStringArg("--scoreboard-key", ScoreboardKey))
    MeleeKey := NormalizeKeyName(ReadStringArg("--melee-key", MeleeKey))
}

ConfigureHotkeys() {
    global TargetWindowTitle, BackgroundInput, ToggleKey, ExitKey

    if BackgroundInput {
        Hotkey(ToggleKey, ToggleScript)
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

SendMouseDown(button) {
    global BackgroundInput
    if BackgroundInput {
        target := ResolveTargetWindow()
        if target = "" {
            return
        }
        whichButton := button = "LButton" ? "Left" : button = "RButton" ? "Right" : button
        try ControlClick(BackgroundClickPoint(target), target, "", whichButton, 1, "D NA Pos")
        return
    }
    Send("{" button " down}")
}

SendMouseUp(button) {
    global BackgroundInput
    if BackgroundInput {
        target := ResolveTargetWindow()
        if target = "" {
            return
        }
        whichButton := button = "LButton" ? "Left" : button = "RButton" ? "Right" : button
        try ControlClick(BackgroundClickPoint(target), target, "", whichButton, 1, "U NA Pos")
        return
    }
    Send("{" button " up}")
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
    global BackgroundInput
    if !BackgroundInput {
        return
    }
    if active {
        target := ResolveTargetWindow()
        if target != "" {
            WinGetPos(&wx, &wy, &ww, &wh, target)
            ToolTip("[AFK] Script Active", wx + 10, wy + 40, 3)
        } else {
            ToolTip("[AFK] Script Active", 10, 40, 3)
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
        SetTimer(MainLoop, -1)
    } else {
        WriteMarker("END")
        ShowStatus("OFF")
        UpdateBackgroundOverlay(false)
    }
}

ExitScript(*) {
    global BackgroundInput

    WriteMarker("EXIT")
    UpdateBackgroundOverlay(false)
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
    global Toggle, HoldLMBTime, PreMeleeWait, VWaitTime, ReticleMode, AdsWait, ScoreboardToggling, ScoreboardKey, MeleeKey

    loop {
        if !Toggle {
            break
        }

        if ReticleMode {
            SendMouseDown("RButton")
            Sleep(AdsWait)
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

        if ReticleMode {
            SendMouseUp("RButton")
        }

        if ScoreboardToggling {
            Sleep(10)
            SendKey(ScoreboardKey)
        }
        Sleep(PreMeleeWait)
        SendKey(MeleeKey)
        Sleep(VWaitTime)
    }
}
