const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
    getServerUrl: () => ipcRenderer.invoke('get-server-url'),
    setServerUrl: (url) => ipcRenderer.invoke('set-server-url', url),
    getSettings: () => ipcRenderer.invoke('get-settings'),
    setSettings: (settings) => ipcRenderer.invoke('set-settings', settings),
    
    // Event listeners
    onOpenSettings: (callback) => ipcRenderer.on('open-settings', callback),
    onRefreshData: (callback) => ipcRenderer.on('refresh-data', callback),
    onSelectCamera: (callback) => ipcRenderer.on('select-camera', (event, idx) => callback(idx)),
    onTogglePlayback: (callback) => ipcRenderer.on('toggle-playback', callback),
    onSkipBack: (callback) => ipcRenderer.on('skip-back', callback),
    onSkipForward: (callback) => ipcRenderer.on('skip-forward', callback),
    onPrevDay: (callback) => ipcRenderer.on('prev-day', callback),
    onNextDay: (callback) => ipcRenderer.on('next-day', callback),
    onGoToday: (callback) => ipcRenderer.on('go-today', callback)
});