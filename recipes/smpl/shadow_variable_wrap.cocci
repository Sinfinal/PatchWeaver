// PatchWeaver shadow_variable_wrap
// Match functions that need shadow state instead of direct global mutation
@ shadow_state_candidate @
identifier fn;
@@
fn(...)
{
  ...
}
