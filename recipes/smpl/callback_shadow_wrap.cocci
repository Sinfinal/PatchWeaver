// PatchWeaver callback_shadow_wrap
// Match functions that need both callback hooks and shadow state
//
// This template is intentionally conservative in P1
// The executor writes a scaffold contract before any handoff to kpatch-build
@ callback_shadow_candidate @
identifier fn;
@@
fn(...)
{
  ...
}
