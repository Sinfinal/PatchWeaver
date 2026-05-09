// PatchWeaver section_change_avoidance_rewrite
// Keep function local fixes and avoid global or section sensitive edits
@ section_change_candidate @
identifier fn;
@@
fn(...)
{
  ...
}
