// Copyright 2012 The Chromium Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.
// API excerpt from pinned ui/native_theme/native_theme.h, verified by source replay.

  enum class PreferredColorScheme {
    kNoPreference = 0,
    kLight = 1,
    kDark = 2,
    kMaxValue = kDark,
  };

  enum class PreferredContrast {
    kNoPreference = 0,
    kMore = 1,
    kLess = 2,
    kCustom = 3,  // E.g. forced colors outside of a contrast-related setting.
    kMaxValue = kCustom,
  };

  static NativeTheme* GetInstanceForNativeUi();

  ColorProviderKey::ForcedColors forced_colors() const {
    return forced_colors_;
  }

  PreferredColorScheme preferred_color_scheme() const {
    return preferred_color_scheme_;
  }

  PreferredContrast preferred_contrast() const { return preferred_contrast_; }
