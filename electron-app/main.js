const { app, BrowserWindow, ipcMain, Menu, shell, dialog } = require('electron');
const path = require('path');
const Store = require('electron-store');

// Initialize settings store
const store = new Store({
    defaults: {
        serverUrl: 'http://localhost:8766',
        shinobiUrl: 'http://localhost:8080',
        windowBounds: { width: 1400, height: 900 },
        alwaysOnTop: false,
        autoPlay: true
    }
});

let mainWindow;

function createWindow() {
    const { width, height } = store.get('windowBounds');
    
    mainWindow = new BrowserWindow({
        width: width,
        height: height,
        minWidth: 900,
        minHeight: 600,
        title: 'Surveillance Viewer',
        icon: path.join(__dirname, 'src', 'icon.png'),
        webPreferences: {
            nodeIntegration: false,
            contextIsolation: true,
            preload: path.join(__dirname, 'preload.js')
        },
        backgroundColor: '#0a0a0f',
        show: false
    });

    mainWindow.loadFile(path.join(__dirname, 'src', 'index.html'));

    mainWindow.once('ready-to-show', () => {
        mainWindow.show();
        mainWindow.setAlwaysOnTop(store.get('alwaysOnTop'));
    });

    mainWindow.on('resize', () => {
        const { width, height } = mainWindow.getBounds();
        store.set('windowBounds', { width, height });
    });

    createMenu();

    if (process.argv.includes('--dev')) {
        mainWindow.webContents.openDevTools();
    }

    mainWindow.on('closed', () => {
        mainWindow = null;
    });
}

function createMenu() {
    const template = [
        {
            label: 'File',
            submenu: [
                {
                    label: 'Settings',
                    accelerator: 'CmdOrCtrl+,',
                    click: () => mainWindow.webContents.send('open-settings')
                },
                { type: 'separator' },
                {
                    label: 'Refresh',
                    accelerator: 'CmdOrCtrl+R',
                    click: () => mainWindow.webContents.send('refresh-data')
                },
                { type: 'separator' },
                { role: 'quit' }
            ]
        },
        {
            label: 'View',
            submenu: [
                {
                    label: 'Always on Top',
                    type: 'checkbox',
                    checked: store.get('alwaysOnTop'),
                    click: (menuItem) => {
                        store.set('alwaysOnTop', menuItem.checked);
                        mainWindow.setAlwaysOnTop(menuItem.checked);
                    }
                },
                { type: 'separator' },
                { role: 'togglefullscreen' },
                { type: 'separator' },
                { role: 'toggleDevTools' }
            ]
        },
        {
            label: 'Playback',
            submenu: [
                {
                    label: 'Play/Pause',
                    accelerator: 'Space',
                    click: () => mainWindow.webContents.send('toggle-playback')
                },
                {
                    label: 'Skip Back 30s',
                    accelerator: 'Left',
                    click: () => mainWindow.webContents.send('skip-back')
                },
                {
                    label: 'Skip Forward 30s',
                    accelerator: 'Right',
                    click: () => mainWindow.webContents.send('skip-forward')
                },
                { type: 'separator' },
                {
                    label: 'Previous Day',
                    accelerator: 'CmdOrCtrl+Left',
                    click: () => mainWindow.webContents.send('prev-day')
                },
                {
                    label: 'Next Day',
                    accelerator: 'CmdOrCtrl+Right',
                    click: () => mainWindow.webContents.send('next-day')
                },
                {
                    label: 'Today',
                    accelerator: 'CmdOrCtrl+T',
                    click: () => mainWindow.webContents.send('go-today')
                }
            ]
        },
        {
            label: 'Cameras',
            submenu: [
                {
                    label: 'Camera 1',
                    accelerator: 'CmdOrCtrl+1',
                    click: () => mainWindow.webContents.send('select-camera', 0)
                },
                {
                    label: 'Camera 2',
                    accelerator: 'CmdOrCtrl+2',
                    click: () => mainWindow.webContents.send('select-camera', 1)
                },
                {
                    label: 'Camera 3',
                    accelerator: 'CmdOrCtrl+3',
                    click: () => mainWindow.webContents.send('select-camera', 2)
                },
                {
                    label: 'Camera 4',
                    accelerator: 'CmdOrCtrl+4',
                    click: () => mainWindow.webContents.send('select-camera', 3)
                }
            ]
        },
        {
            label: 'Help',
            submenu: [
                {
                    label: 'Open Shinobi',
                    click: () => shell.openExternal(store.get('shinobiUrl'))
                },
                {
                    label: 'Open Web UI',
                    click: () => shell.openExternal(store.get('serverUrl'))
                },
                { type: 'separator' },
                {
                    label: 'About',
                    click: () => {
                        dialog.showMessageBox(mainWindow, {
                            type: 'info',
                            title: 'About Surveillance Viewer',
                            message: 'Surveillance Viewer v2.0.0',
                            detail: 'Desktop application for viewing camera recordings and detection events.\n\nFeatures:\n• 24-hour timeline view\n• Event markers for person/car/truck detection\n• Click-to-seek on timeline\n• Automatic recording continuation'
                        });
                    }
                }
            ]
        }
    ];

    const menu = Menu.buildFromTemplate(template);
    Menu.setApplicationMenu(menu);
}

// IPC Handlers
ipcMain.handle('get-server-url', () => store.get('serverUrl'));

ipcMain.handle('set-server-url', (event, url) => {
    store.set('serverUrl', url);
    return true;
});

ipcMain.handle('get-settings', () => ({
    serverUrl: store.get('serverUrl'),
    shinobiUrl: store.get('shinobiUrl'),
    alwaysOnTop: store.get('alwaysOnTop'),
    autoPlay: store.get('autoPlay')
}));

ipcMain.handle('set-settings', (event, settings) => {
    if (settings.serverUrl) store.set('serverUrl', settings.serverUrl);
    if (settings.shinobiUrl) store.set('shinobiUrl', settings.shinobiUrl);
    if (settings.alwaysOnTop !== undefined) {
        store.set('alwaysOnTop', settings.alwaysOnTop);
        mainWindow.setAlwaysOnTop(settings.alwaysOnTop);
    }
    if (settings.autoPlay !== undefined) store.set('autoPlay', settings.autoPlay);
    return true;
});

app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') {
        app.quit();
    }
});

app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
        createWindow();
    }
});