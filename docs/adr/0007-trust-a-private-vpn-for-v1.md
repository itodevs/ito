# Trust a private network for v1

Ito v1 runs only inside a private network whose members are trusted, such as local Wi-Fi during early development or a private VPN when the headset, server, and robot are not on the same LAN. The server, web client, and robot drivers do not implement application-layer authentication or authorization, and the server must not be exposed for public control. This keeps the first system small while making public deployment explicitly dependent on the future driver-authentication, pilot-authorization, and transport-security design.
