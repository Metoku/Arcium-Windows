// Copyright 2024 The Chromium Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

// API excerpt from pinned Chromium 156.0.8078.47 BrowserWindowInterface.
// Documentation comments are omitted; source replay verifies the declarations.
  enum Type {
    TYPE_NORMAL,
    TYPE_POPUP,
    TYPE_APP,
#if !BUILDFLAG(IS_ANDROID)
    TYPE_DEVTOOLS,
#endif
    TYPE_APP_POPUP,
#if !BUILDFLAG(IS_ANDROID)
    TYPE_PICTURE_IN_PICTURE,
#endif
#if BUILDFLAG(IS_ANDROID)
    TYPE_CUSTOM_TAB,
#endif
  };
  virtual Type GetType() const = 0;
  virtual Profile* GetProfile() = 0;
  virtual const Profile* GetProfile() const = 0;
