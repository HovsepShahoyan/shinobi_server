const { app, BrowserWindow, ipcMain, Menu, shell, dialog } = require('electron');
const path = require('path');
const Store = require('electron-store');

// Initialize settings store
const store = new Store({
    defaults: {
        serverUrl: 'http://localhost:8766',
        windowBounds: { width: 1400, height: 900 },
        alwaysOnTop: false
    }
});

let mainWindow;

function createWindow() {
    const { width, height } = store.get('windowBounds');
    
    mainWindow = new BrowserWindow({
        width: width,
        height: height,
        minWidth: 800,
        minHeight: 600,
        title: 'Camera Viewer',
        icon: path.join(__dirname, 'src', 'icon.png'),
        webPreferences: {
            nodeIntegration: false,
            contextIsolation: true,
            preload: path.join(__dirname, 'preload.js')
        },
        backgroundColor: '#0d1117',
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
                    click: () => {
                        mainWindow.webContents.send('open-settings');
                    }
                },
                { type: 'separator' },
                {
                    label: 'Refresh',
                    accelerator: 'CmdOrCtrl+R',
                    click: () => {
                        mainWindow.webContents.send('refresh-data');
                    }
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
            label: 'Cameras',
            submenu: [
                {
                    label: 'Camera 1',
                    accelerator: 'CmdOrCtrl+1',
                    click: () => {
                        mainWindow.webContents.send('select-camera', 0);
                    }
                },
                {
                    label: 'Camera 2',
                    accelerator: 'CmdOrCtrl+2',
                    click: () => {
                        mainWindow.webContents.send('select-camera', 1);
                    }
                }
            ]
        },
        {
            label: 'Help',
            submenu: [
                {
                    label: 'Open Shinobi',
                    click: () => {
                        shell.openExternal('http://localhost:8080');
                    }
                },
                {
                    label: 'Open Web UI',
                    click: () => {
                        shell.openExternal(store.get('serverUrl'));
                    }
                },
                { type: 'separator' },
                {
                    label: 'About',
                    click: () => {
                        dialog.showMessageBox(mainWindow, {
                            type: 'info',
                            title: 'About Camera Viewer',
                            message: 'Camera Viewer v1.0.0',
                            detail: 'Desktop application for viewing camera recordings and events.\n\nStreams video from Shinobi NVR.'
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
ipcMain.handle('get-server-url', () => {
    return store.get('serverUrl');
});

ipcMain.handle('set-server-url', (event, url) => {
    store.set('serverUrl', url);
    return true;
});

ipcMain.handle('get-settings', () => {
    return {
        serverUrl: store.get('serverUrl'),
        alwaysOnTop: store.get('alwaysOnTop')
    };
});

ipcMain.handle('set-settings', (event, settings) => {
    if (settings.serverUrl) {
        store.set('serverUrl', settings.serverUrl);
    }
    if (settings.alwaysOnTop !== undefined) {
        store.set('alwaysOnTop', settings.alwaysOnTop);
        mainWindow.setAlwaysOnTop(settings.alwaysOnTop);
    }
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