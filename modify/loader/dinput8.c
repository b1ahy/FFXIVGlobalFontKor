// Korean font loader for the FFXIV global client (dinput8.dll proxy).
//
// The game imports DINPUT8.dll, so this DLL is loaded at startup. It hooks the game's import of
// CreateFileW and, without touching any game file:
//   * when the game opens sqpack\ffxiv\000000.win32.index / .index2, it opens a copy of the real
//     index in which the font entries listed in koreanfont\files.txt point at an extra .dat file;
//   * when the game opens that extra 000000.win32.datN, it opens koreanfont\000000.win32.dat.
// The copy is rebuilt from the real index on every launch, so it follows game updates.

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <wchar.h>
#include <wctype.h>

#define MAX_FILES 64
#define INDEX_DAT_COUNT_OFFSET 0x450  // sqindex header (0x400) + segment 2 descriptor Count

typedef HANDLE(WINAPI *CreateFileW_t)(LPCWSTR, DWORD, DWORD, LPSECURITY_ATTRIBUTES, DWORD, DWORD, HANDLE);
typedef HRESULT(WINAPI *DirectInput8Create_t)(HINSTANCE, DWORD, REFIID, LPVOID *, void *);

typedef struct {
    uint64_t hash1;   // index:  (folder crc << 32) | file name crc
    uint32_t hash2;   // index2: full path crc
    uint32_t offset;  // entry offset in our .dat
} FontFile;

static CreateFileW_t g_createFileW;
static FontFile g_files[MAX_FILES];
static int g_fileCount;
static WCHAR g_dataDir[MAX_PATH];
static WCHAR g_datPath[MAX_PATH];
static WCHAR g_indexPath[2][MAX_PATH];  // patched copies of .index and .index2
static int g_datId = -1;                // the dat number our files get in the patched index
static BOOL g_prepared, g_ready;
static CRITICAL_SECTION g_lock;

static void LogLine(const char *fmt, ...) {
    WCHAR path[MAX_PATH];
    char buf[1024];
    va_list ap;
    SYSTEMTIME t;
    DWORD written;
    HANDLE h;
    int n;

    swprintf(path, MAX_PATH, L"%ls\\loader.log", g_dataDir);
    h = (g_createFileW ? g_createFileW : CreateFileW)(path, FILE_APPEND_DATA, FILE_SHARE_READ | FILE_SHARE_WRITE, NULL,
                                                      OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (h == INVALID_HANDLE_VALUE)
        return;
    GetLocalTime(&t);
    n = snprintf(buf, sizeof buf, "[%04d-%02d-%02d %02d:%02d:%02d pid %lu] ", t.wYear, t.wMonth, t.wDay, t.wHour,
                 t.wMinute, t.wSecond, GetCurrentProcessId());
    va_start(ap, fmt);
    n += vsnprintf(buf + n, sizeof buf - n - 2, fmt, ap);
    va_end(ap);
    if (n > (int)sizeof buf - 2)
        n = sizeof buf - 2;
    buf[n++] = '\r';
    buf[n++] = '\n';
    WriteFile(h, buf, n, &written, NULL);
    CloseHandle(h);
}

static BOOL ReadWholeFile(LPCWSTR path, BYTE **data, DWORD *size) {
    HANDLE h = g_createFileW(path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, NULL, OPEN_EXISTING,
                             FILE_ATTRIBUTE_NORMAL, NULL);
    DWORD read = 0;
    if (h == INVALID_HANDLE_VALUE)
        return FALSE;
    *size = GetFileSize(h, NULL);
    *data = (BYTE *)HeapAlloc(GetProcessHeap(), 0, *size ? *size : 1);
    if (!*data || !ReadFile(h, *data, *size, &read, NULL) || read != *size) {
        CloseHandle(h);
        if (*data)
            HeapFree(GetProcessHeap(), 0, *data);
        return FALSE;
    }
    CloseHandle(h);
    return TRUE;
}

static BOOL WriteWholeFile(LPCWSTR path, const BYTE *data, DWORD size) {
    HANDLE h = g_createFileW(path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    DWORD written = 0;
    BOOL ok;
    if (h == INVALID_HANDLE_VALUE)
        return FALSE;
    ok = WriteFile(h, data, size, &written, NULL) && written == size;
    CloseHandle(h);
    return ok;
}

static BOOL LoadManifest(void) {
    WCHAR path[MAX_PATH];
    BYTE *data;
    DWORD size;
    char *line, *next;

    swprintf(path, MAX_PATH, L"%ls\\files.txt", g_dataDir);
    if (!ReadWholeFile(path, &data, &size))
        return FALSE;
    data = (BYTE *)HeapReAlloc(GetProcessHeap(), 0, data, size + 1);
    data[size] = 0;
    for (line = (char *)data; line && *line && g_fileCount < MAX_FILES; line = next) {
        unsigned long long h1;
        unsigned int h2, off;
        next = strchr(line, '\n');
        if (next)
            *next++ = 0;
        if (sscanf(line, "%llx %x %u", &h1, &h2, &off) == 3) {
            g_files[g_fileCount].hash1 = h1;
            g_files[g_fileCount].hash2 = h2;
            g_files[g_fileCount].offset = off;
            g_fileCount++;
        }
    }
    HeapFree(GetProcessHeap(), 0, data);
    return g_fileCount > 0;
}

// Points every manifest entry of an .index (entrySize 16) or .index2 (entrySize 8) at our dat.
// Returns FALSE unless every entry was found exactly once.
static BOOL PatchIndex(BYTE *data, DWORD size, int entrySize, int datId) {
    uint32_t headerSize, segOffset, segSize, i;
    int f, found[MAX_FILES] = {0};

    if (size < 0x800 || memcmp(data, "SqPack", 6) != 0)
        return FALSE;
    headerSize = *(uint32_t *)(data + 0xC);
    segOffset = *(uint32_t *)(data + headerSize + 8);
    segSize = *(uint32_t *)(data + headerSize + 0xC);
    if ((uint64_t)segOffset + segSize > size)
        return FALSE;
    for (i = 0; i + entrySize <= segSize; i += entrySize) {
        BYTE *e = data + segOffset + i;
        uint32_t *locator = (uint32_t *)(e + (entrySize == 16 ? 8 : 4));
        for (f = 0; f < g_fileCount; f++) {
            BOOL match = entrySize == 16 ? *(uint64_t *)e == g_files[f].hash1 : *(uint32_t *)e == g_files[f].hash2;
            if (!match)
                continue;
            if (*locator & 1)  // hash collision entry; resolved through another segment
                return FALSE;
            *locator = ((uint32_t)datId << 1) | (g_files[f].offset >> 3);
            found[f]++;
        }
    }
    for (f = 0; f < g_fileCount; f++)
        if (found[f] != 1)
            return FALSE;
    *(uint32_t *)(data + INDEX_DAT_COUNT_OFFSET) = (uint32_t)datId + 1;
    return TRUE;
}

// Writes the patched index somewhere the game can open it. Another running client may hold the
// file open; if it already has the same content it is reused, otherwise a per-process name is used.
static BOOL StoreIndex(int which, const BYTE *data, DWORD size) {
    static const WCHAR *names[2] = {L"000000.win32.index", L"000000.win32.index2"};
    WCHAR dirs[2][MAX_PATH], path[MAX_PATH];
    int d;

    swprintf(dirs[0], MAX_PATH, L"%ls\\cache", g_dataDir);
    GetTempPathW(MAX_PATH, path);
    swprintf(dirs[1], MAX_PATH, L"%lsffxiv-korean-font", path);
    for (d = 0; d < 2; d++) {
        BYTE *old;
        DWORD oldSize;
        CreateDirectoryW(dirs[d], NULL);
        swprintf(path, MAX_PATH, L"%ls\\%ls", dirs[d], names[which]);
        if (ReadWholeFile(path, &old, &oldSize)) {
            BOOL same = oldSize == size && memcmp(old, data, size) == 0;
            HeapFree(GetProcessHeap(), 0, old);
            if (same) {
                wcscpy(g_indexPath[which], path);
                return TRUE;
            }
        }
        if (WriteWholeFile(path, data, size)) {
            wcscpy(g_indexPath[which], path);
            return TRUE;
        }
        swprintf(path, MAX_PATH, L"%ls\\%ls.%lu", dirs[d], names[which], GetCurrentProcessId());
        if (WriteWholeFile(path, data, size)) {
            wcscpy(g_indexPath[which], path);
            return TRUE;
        }
    }
    return FALSE;
}

// realIndexPath: the path the game used for .index or .index2; the sibling is derived from it.
static void Prepare(LPCWSTR realIndexPath) {
    WCHAR paths[2][MAX_PATH];
    BYTE *data[2] = {NULL, NULL};
    DWORD size[2];
    size_t len = wcslen(realIndexPath);
    int which, datId;

    g_prepared = TRUE;
    if (len + 2 > MAX_PATH)
        return;
    wcscpy(paths[0], realIndexPath);
    if (paths[0][len - 1] == L'2')
        paths[0][len - 1] = 0;
    swprintf(paths[1], MAX_PATH, L"%ls2", paths[0]);

    for (which = 0; which < 2; which++) {
        if (!ReadWholeFile(paths[which], &data[which], &size[which])) {
            LogLine("cannot read %ls", paths[which]);
            goto done;
        }
    }
    datId = (int)*(uint32_t *)(data[0] + INDEX_DAT_COUNT_OFFSET);
    if (datId < 1 || datId > 7 || *(uint32_t *)(data[1] + INDEX_DAT_COUNT_OFFSET) != (uint32_t)datId) {
        LogLine("unexpected dat count %d; not loading", datId);
        goto done;
    }
    if (!PatchIndex(data[0], size[0], 16, datId) || !PatchIndex(data[1], size[1], 8, datId)) {
        LogLine("font entries not found in the game index; not loading (game files changed?)");
        goto done;
    }
    if (!StoreIndex(0, data[0], size[0]) || !StoreIndex(1, data[1], size[1])) {
        LogLine("cannot write the patched index; not loading");
        goto done;
    }
    g_datId = datId;
    g_ready = TRUE;
    LogLine("ready: %d font files served as 000000.win32.dat%d, index copy %ls", g_fileCount, datId, g_indexPath[0]);

done:
    for (which = 0; which < 2; which++)
        if (data[which])
            HeapFree(GetProcessHeap(), 0, data[which]);
}

// Case-insensitive check that path ends with "sqpack\ffxiv\<name>" (either slash).
static BOOL EndsWithSqpackFile(LPCWSTR path, LPCWSTR name) {
    WCHAR tail[64];
    size_t lp = wcslen(path), lt, i;
    swprintf(tail, 64, L"sqpack\\ffxiv\\%ls", name);
    lt = wcslen(tail);
    if (lp < lt)
        return FALSE;
    if (lp > lt && path[lp - lt - 1] != L'\\' && path[lp - lt - 1] != L'/')
        return FALSE;
    for (i = 0; i < lt; i++) {
        WCHAR a = path[lp - lt + i], b = tail[i];
        if (a == L'/')
            a = L'\\';
        if (towlower(a) != towlower(b))
            return FALSE;
    }
    return TRUE;
}

static HANDLE WINAPI CreateFileW_Hook(LPCWSTR name, DWORD access, DWORD share, LPSECURITY_ATTRIBUTES sa,
                                      DWORD disposition, DWORD flags, HANDLE templ) {
    if (name) {
        int which = EndsWithSqpackFile(name, L"000000.win32.index") ? 0
                  : EndsWithSqpackFile(name, L"000000.win32.index2") ? 1 : -1;
        if (which >= 0) {
            EnterCriticalSection(&g_lock);
            if (!g_prepared)
                Prepare(name);
            LeaveCriticalSection(&g_lock);
            if (g_ready)
                return g_createFileW(g_indexPath[which], access, share, sa, disposition, flags, templ);
        } else if (g_ready) {
            WCHAR datName[32];
            swprintf(datName, 32, L"000000.win32.dat%d", g_datId);
            if (EndsWithSqpackFile(name, datName))
                return g_createFileW(g_datPath, access, share, sa, disposition, flags, templ);
        }
    }
    return g_createFileW(name, access, share, sa, disposition, flags, templ);
}

static BOOL HookImport(HMODULE module, const char *dll, const char *func, void *hook, void **original) {
    BYTE *base = (BYTE *)module;
    IMAGE_NT_HEADERS *nt = (IMAGE_NT_HEADERS *)(base + ((IMAGE_DOS_HEADER *)base)->e_lfanew);
    IMAGE_DATA_DIRECTORY dir = nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT];
    IMAGE_IMPORT_DESCRIPTOR *imp;

    if (!dir.VirtualAddress)
        return FALSE;
    for (imp = (IMAGE_IMPORT_DESCRIPTOR *)(base + dir.VirtualAddress); imp->Name; imp++) {
        IMAGE_THUNK_DATA *names, *funcs;
        if (_stricmp((const char *)(base + imp->Name), dll) != 0 || !imp->OriginalFirstThunk)
            continue;
        names = (IMAGE_THUNK_DATA *)(base + imp->OriginalFirstThunk);
        funcs = (IMAGE_THUNK_DATA *)(base + imp->FirstThunk);
        for (; names->u1.AddressOfData; names++, funcs++) {
            DWORD old;
            if (IMAGE_SNAP_BY_ORDINAL(names->u1.Ordinal))
                continue;
            if (strcmp((const char *)((IMAGE_IMPORT_BY_NAME *)(base + names->u1.AddressOfData))->Name, func) != 0)
                continue;
            if (!VirtualProtect(&funcs->u1.Function, sizeof(void *), PAGE_READWRITE, &old))
                return FALSE;
            *original = (void *)funcs->u1.Function;
            funcs->u1.Function = (ULONG_PTR)hook;
            VirtualProtect(&funcs->u1.Function, sizeof(void *), old, &old);
            return TRUE;
        }
    }
    return FALSE;
}

static void Init(HMODULE self) {
    WCHAR *slash;
    DWORD attr;

    GetModuleFileNameW(self, g_dataDir, MAX_PATH);
    slash = wcsrchr(g_dataDir, L'\\');
    if (!slash)
        return;
    wcscpy(slash, L"\\koreanfont");
    swprintf(g_datPath, MAX_PATH, L"%ls\\000000.win32.dat", g_dataDir);
    attr = GetFileAttributesW(g_datPath);
    if (attr == INVALID_FILE_ATTRIBUTES)
        return;  // no font data next to the DLL: behave as a plain dinput8 proxy
    g_createFileW = CreateFileW;
    if (!LoadManifest()) {
        LogLine("cannot read files.txt; not loading");
        return;
    }
    InitializeCriticalSection(&g_lock);
    if (!HookImport(GetModuleHandleW(NULL), "kernel32.dll", "CreateFileW", (void *)CreateFileW_Hook,
                    (void **)&g_createFileW)) {
        g_createFileW = CreateFileW;
        LogLine("cannot hook CreateFileW; not loading");
    }
}

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID reserved) {
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(instance);
        Init(instance);
    }
    return TRUE;
}

__declspec(dllexport) HRESULT WINAPI DirectInput8Create(HINSTANCE inst, DWORD version, REFIID riid, LPVOID *out,
                                                         void *outer) {
    static DirectInput8Create_t real;
    if (!real) {
        WCHAR path[MAX_PATH];
        HMODULE h;
        UINT n = GetSystemDirectoryW(path, MAX_PATH);
        if (!n || n + 13 > MAX_PATH)
            return E_FAIL;
        wcscat(path, L"\\dinput8.dll");
        h = LoadLibraryW(path);
        if (h)
            real = (DirectInput8Create_t)GetProcAddress(h, "DirectInput8Create");
        if (!real)
            return E_FAIL;
    }
    return real(inst, version, riid, out, outer);
}
