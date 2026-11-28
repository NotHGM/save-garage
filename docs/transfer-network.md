# The PS5 reconnects without starting the upload

If the command connection opens repeatedly but no data connection arrives on TCP port 1005, check that the computer and PS5 are on the same home network and that client isolation is disabled. Guest Wi-Fi may isolate devices. IPv6 must be enabled on the adapter connected to the console.

On a trusted Windows home network using the Private profile, a firewall rule can allow the portable copy of Save Garage to receive data from the local subnet. If Windows Firewall is blocking this connection, open PowerShell as administrator in the extracted Save Garage folder and run:

~~~powershell
$program = (Resolve-Path -LiteralPath '.\app\python\python.exe' -ErrorAction Stop).Path
New-NetFirewallRule -DisplayName 'Save Garage PS5 data TCP 1005' -Direction Inbound -Action Allow -Program $program -Profile Private -Protocol TCP -LocalPort 1005 -RemoteAddress LocalSubnet
~~~

Keep Save Garage open, then search again on the console. A line containing `[data] connection from` in the transfer log indicates that the connection reached the data listener.

To remove the rule:

~~~powershell
Remove-NetFirewallRule -DisplayName 'Save Garage PS5 data TCP 1005'
~~~
