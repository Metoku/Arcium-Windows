The profile keep-alive header, logger and metrics XML fixtures are complete
Chromium 156.0.8078.47 source files, stored with LF endings:

- https://github.com/chromium/chromium/blob/156.0.8078.47/chrome/browser/profiles/keep_alive/profile_keep_alive_types.h
- https://github.com/chromium/chromium/blob/156.0.8078.47/chrome/browser/profiles/keep_alive/profile_keep_alive_types.cc
- https://github.com/chromium/chromium/blob/156.0.8078.47/tools/metrics/histograms/metadata/profile/enums.xml

The Windows port copies the three shared enum/logger/metric hunks from
Arcium's Mac-native settings patch, preserving its existing numeric value 47:

https://github.com/dr-baker/Arcium-macOS/blob/19e546db4ee778d05d3e1dfc3035ca270a458ad5/patches/personal/arcium-native-settings-macos.patch

Tests first compile a reference to the missing origin against the unmodified
types and require failure, then apply the port, compile the complete actual
header/logger and execute its stream output. The contract supplies only small
build_config and NOTREACHED transitive support stubs. This checks the reported
type error, enum maximum and logger; it is not a full Chromium compilation.
