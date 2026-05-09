// PatchWeaver state_preserving_wrap
// Match functions that need explicit state carry over across patch versions
@ state_preserving_candidate @
identifier fn;
@@
fn(...)
{
  ...
}
