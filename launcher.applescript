-- Meeting Notetaker launcher
-- Opens the Flask app at http://127.0.0.1:5002.
-- Always kills any leftover server (and orphaned recorder helper) and starts a
-- FRESH server so the latest code is loaded, then waits for it to respond to
-- HTTP and opens the URL.

on run
	set projectDir to "/Users/martinstuebler/Documents/my_projects/meeting-notetaker"
	set py to projectDir & "/venv/bin/python"
	set logFile to projectDir & "/launcher.log"
	set theURL to "http://127.0.0.1:5002"

	-- Always start a FRESH server. A server left over from a previous launch
	-- keeps the OLD code in memory: app.py runs Flask with use_reloader=False, so
	-- editing recorder.py does not reload a running process. Reusing that old
	-- server is exactly why new capture code never took effect (the stale ffmpeg
	-- process). So: kill any old server, cleanly stop any orphaned recorder helper
	-- (SIGINT finalizes its WAV), wait for the port to free, then start once.
	--
	-- We match on the ABSOLUTE app.py path, not the python binary: the venv
	-- python is a shim that re-execs the Homebrew framework Python, so the live
	-- process line is ".../MacOS/Python app.py" with no venv path in it. The
	-- script argument is the only stable, unique token, so we start the server
	-- with app.py's absolute path (below) and match it here.
	--
	-- The kill patterns use a [b]racket on the first char so the regex still
	-- matches the target process but does NOT match this pkill command line
	-- itself (whose text contains the literal pattern) - the classic ps-grep
	-- self-match trick. `; true` keeps a no-match exit (non-zero) from aborting.
	do shell script "/usr/bin/pkill -f '[m]eeting-notetaker/app.py' ; /usr/bin/pkill -INT -f '[s]ysaudio-rec' ; true"

	-- Wait for port 5002 to actually free (up to ~5s) so the fresh server binds.
	repeat 10 times
		set portBusy to true
		try
			do shell script "/usr/sbin/lsof -nP -iTCP:5002 -sTCP:LISTEN >/dev/null 2>&1"
		on error
			set portBusy to false
		end try
		if not portBusy then exit repeat
		delay 0.5
	end repeat

	-- Start the server once, fully detached, logging stdout+stderr to
	-- launcher.log. The server runs inside a subshell ( ... & ) so that
	-- `do shell script` returns immediately. Without the subshell it blocks
	-- until the server exits, so the poll-and-open code below never ran and
	-- the browser never opened.
	do shell script "cd " & quoted form of projectDir & " && ( /usr/bin/nohup " & quoted form of py & " " & quoted form of (projectDir & "/app.py") & " < /dev/null >> " & quoted form of logFile & " 2>&1 & )"

	-- Poll until it answers HTTP, up to ~15s (30 x 0.5s)
	set isUp to false
	repeat 30 times
		try
			do shell script "/usr/bin/curl -s -o /dev/null --max-time 1 " & quoted form of theURL
			set isUp to true
			exit repeat
		end try
		delay 0.5
	end repeat

	if isUp then
		-- Use the `open` command (LaunchServices) rather than `open location`.
		-- `open location` can silently fail to hand the URL to the default
		-- browser from a Dock-launched applet, which is why the browser was
		-- not opening. `/usr/bin/open` reliably opens it, and any failure is
		-- surfaced instead of swallowed.
		try
			do shell script "/usr/bin/open " & quoted form of theURL
		on error errMsg number errNum
			display dialog "Server is running but the browser could not be opened (" & errNum & "): " & errMsg & return & return & "Open this URL manually: " & theURL buttons {"OK"} default button "OK" with icon caution
		end try
	else
		display dialog "Meeting Notetaker server did not start within 15 seconds. Check launcher.log in the project folder." buttons {"OK"} default button "OK" with icon caution
	end if
end run
