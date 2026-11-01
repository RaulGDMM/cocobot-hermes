#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shellapi.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/*
 * mtmd-video wrapper — workaround for llama.cpp Windows subprocess
 * stdin deadlock (issue #24429).
 *
 * The llama.cpp server feeds the raw video into the child's stdin pipe
 * via a feeder thread, but keeps an extra read-end handle (hStdInput)
 * that is only closed in join/destroy. When the child (ffprobe on a
 * faststart MP4) exits after reading just the header, nobody drains the
 * pipe any more and the feeder thread blocks in fwrite forever.
 *
 * This wrapper IS the child. It first drains its own stdin (the pipe)
 * into a temp file, rewrites "pipe:0" / "cache:pipe:0" input arguments
 * to that file, then launches <name>_real.exe and relays stdout.
 *
 * Build:  x86_64-w64-mingw32-gcc -O2 -static -Wall -o ffmpeg.exe mtmd-wrapper.c
 *         (same source for ffprobe.exe — the real binary is resolved
 *          at runtime from the wrapper's own file name)
 *
 * Deploy: rename the real ffmpeg.exe/ffprobe.exe to *_real.exe and place
 *         this wrapper (compiled as ffmpeg.exe / ffprobe.exe) beside them.
 * Debug:  run the wrapper with an extra "-mtmddebug" arg to dump the exact
 *         child cmdline to mtmd_wrap_debug.txt next to the wrapper.
 *
 * Tested 2026-08-20 (b10538 server, WSL cross-compiled, 3 MP4 layouts).
 * Do not "improve" without re-running the verification steps in SKILL.md.
 */

#define MAX_ARGV 512

static int is_pipe_input(const char *a)
{
    return strcmp(a, "pipe:0") == 0 || strcmp(a, "cache:pipe:0") == 0;
}

int main(int argc, char **argv)
{
    /* ---- locate <own_base>_real.exe next to this wrapper ---- */
    wchar_t mod[MAX_PATH];
    if (!GetModuleFileNameW(NULL, mod, MAX_PATH)) return 127;
    wchar_t *slash = wcsrchr(mod, L'\\');
    if (!slash) return 127;

    wchar_t base[MAX_PATH];
    wcscpy(base, slash + 1);
    wchar_t *dot = wcsrchr(base, L'.');
    if (dot) *dot = 0;
    *(slash + 1) = 0; /* mod now holds just the directory */

    wchar_t realw[MAX_PATH + 32];
    wsprintfW(realw, L"%s%s_real.exe", mod, base);
    char reala[MAX_PATH + 32];
    if (!WideCharToMultiByte(CP_UTF8, 0, realw, -1, reala, (int)sizeof(reala), NULL, NULL))
        return 127;

    if (GetFileAttributesA(reala) == INVALID_FILE_ATTRIBUTES) {
        fprintf(stderr, "mtmd-wrapper: real binary not found: %s\n", reala);
        return 127;
    }

    /* ---- filter -mtmddebug (WSL env vars don't cross into Win32) ---- */
    int debug = 0;
    int has_pipe = 0;
    int rargc = 0;
    char **rargv = (char **)malloc(sizeof(char *) * argc);
    for (int i = 0; i < argc; i++) {
        if (strcmp(argv[i], "-mtmddebug") == 0) { debug = 1; continue; }
        rargv[rargc++] = argv[i];
    }
    argc = rargc;
    for (int i = 1; i < argc; i++) {
        if (strcmp(rargv[i], "pipe:0") == 0 || strcmp(rargv[i], "cache:pipe:0") == 0) { has_pipe = 1; break; }
    }

    char tmpfile[MAX_PATH] = {0};
    if (has_pipe) {
        HANDLE hIn = GetStdHandle(STD_INPUT_HANDLE);
        if (!hIn || hIn == INVALID_HANDLE_VALUE ||
            GetFileType(hIn) != FILE_TYPE_PIPE) {
            fprintf(stderr, "mtmd-wrapper: pipe input requested but stdin is not a pipe\n");
            return 1;
        }
        /* temp file lives next to this wrapper: the BtbN ffmpeg/ffprobe
         * builds choke on 8.3 short paths (C:\Users\RAL~1\...) from
         * GetTempPathA, and the wrapper dir is always a plain path */
        char dir[MAX_PATH];
        strcpy(dir, reala);
        char *ds = strrchr(dir, '\\');
        if (ds) ds[1] = 0; else dir[0] = 0;
        snprintf(tmpfile, sizeof tmpfile, "%smtmdwrap_%lu_%ld.bin",
                 dir, (unsigned long)GetTickCount(), (long)GetCurrentProcessId());
        FILE *tf = fopen(tmpfile, "wb");
        if (!tf) {
            fprintf(stderr, "mtmd-wrapper: cannot create temp file %s\n", tmpfile);
            return 1;
        }
        /* drain the whole pipe (the server's feeder closes the write end
         * after writing, so ReadFile returns 0 = EOF when it's done) */
        char buf[1 << 20];
        for (;;) {
            DWORD rd = 0;
            if (!ReadFile(hIn, buf, sizeof buf, &rd, NULL)) break;
            if (rd == 0) break;
            if (fwrite(buf, 1, rd, tf) != rd) break;
        }
        fclose(tf);
    }

    /* ---- build the child command line, rewriting the input token ---- */
    /*
     * CreateProcessW contract: when lpApplicationName is set, lpCommandLine
     * MUST still begin with the executable name, otherwise the child's
     * GetCommandLine() has no argv[0] and every arg shifts left (ffmpeg then
     * mis-reads 'quiet' as an input filename, etc.). Prepend the real exe.
     */
    const char *eff[MAX_ARGV];
    for (int i = 1; i < argc; i++)
        eff[i] = (has_pipe && is_pipe_input(rargv[i])) ? tmpfile : rargv[i];

    size_t total = 2 + wcslen(realw) + 3;
    for (int i = 1; i < argc; i++) {
        const char *a = eff[i];
        total += (size_t)(MultiByteToWideChar(CP_UTF8, 0, a, -1, NULL, 0) - 1)
               + (strchr(a, ' ') ? 2 : 0) + 1; /* quotes + space */
    }
    wchar_t *cmdline = (wchar_t *)malloc(total * sizeof(wchar_t));
    if (!cmdline) return 1;
    cmdline[0] = 0;
    /* first token: the real executable, quoted (its path has backslashes/spaces-safe) */
    wcscat(cmdline, L"\"");
    wcscat(cmdline, realw);
    wcscat(cmdline, L"\"");
    for (int i = 1; i < argc; i++) {
        const char *a = eff[i];
        if (cmdline[0]) wcscat(cmdline, L" ");
        if (strchr(a, ' ')) wcscat(cmdline, L"\"");
        MultiByteToWideChar(CP_UTF8, 0, a, -1,
                            cmdline + wcslen(cmdline),
                            (int)(total - wcslen(cmdline)));
        if (strchr(a, ' ')) wcscat(cmdline, L"\"");
    }

    if (debug) {
        /* debug file next to the wrapper (mod = its dir); avoids any
         * non-ASCII path issues and is readable from WSL */
        wchar_t dbgpath[MAX_PATH + 32];
        wsprintfW(dbgpath, L"%smtmd_wrap_debug.txt", mod);
        char dbgpatha[MAX_PATH + 32];
        WideCharToMultiByte(CP_UTF8, 0, dbgpath, -1, dbgpatha,
                            (int)sizeof dbgpatha, NULL, NULL);
        FILE *df = fopen(dbgpatha, "a");
        if (df) {
            fprintf(df, "=== real=%s argc=%d tmp=%s\n",
                    reala, argc, tmpfile[0] ? tmpfile : "(none)");
            for (int i = 1; i < argc; i++) fprintf(df, "  argv[%d]=[%s]\n", i, rargv[i]);
            fprintf(df, "  CMDLINE=[%ls]\n", cmdline);
            fclose(df);
        }
    }

    /* ---- launch the real binary, inheriting stdout/stderr ---- */
    STARTUPINFOW si;
    ZeroMemory(&si, sizeof si);
    si.cb = sizeof si;
    PROCESS_INFORMATION pi;
    ZeroMemory(&pi, sizeof pi);
    if (!CreateProcessW(realw, cmdline, NULL, NULL, TRUE, 0, NULL, NULL, &si, &pi)) {
        fprintf(stderr, "mtmd-wrapper: CreateProcess(%s) failed: %lu\n", reala, GetLastError());
        if (tmpfile[0]) DeleteFileA(tmpfile);
        return 1;
    }
    WaitForSingleObject(pi.hProcess, INFINITE);
    DWORD code = 0;
    GetExitCodeProcess(pi.hProcess, &code);
    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);
    free(cmdline);
    if (tmpfile[0]) DeleteFileA(tmpfile);
    return (int)code;
}
