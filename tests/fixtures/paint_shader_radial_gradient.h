// Copyright 2017 The Chromium Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

// Verbatim API excerpt from Chromium 156.0.8078.47 cc/paint/paint_shader.h.
// The pinned-source replay verifies this declaration against upstream.
  static sk_sp<PaintShader> MakeRadialGradient(
      const SkPoint& center,
      SkScalar radius,
      const SkColor4f colors[],
      const SkScalar pos[],
      int color_count,
      SkTileMode mode,
      SkGradient::Interpolation interpolation = DefaultInterpolation(),
      uint32_t flags = 0,
      const SkMatrix* local_matrix = nullptr,
      SkColor4f fallback_color = SkColors::kTransparent);
