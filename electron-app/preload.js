const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
    getServerUrl: () => ipcRenderer.invoke('get-server-url'),
    setServerUrl: (url) => ipcRenderer.invoke('set-server-url', url),
    getSettings: () => ipcRenderer.invoke('get-settings'),
    setSettings: (settings) => ipcRenderer.invoke('set-settings', settings),
    
    onOpenSettings: (callback) => ipcRenderer.on('open-settings', callback),
    onRefreshData: (callback) => ipcRenderer.on('refresh-data', callback),
    onSelectCamera: (callback) => ipcRenderer.on('select-camera', (event, index) => callback(index)),
    
    removeAllListeners: (channel) => ipcRenderer.removeAllListeners(channel)
});

console.log('Preload script loaded');