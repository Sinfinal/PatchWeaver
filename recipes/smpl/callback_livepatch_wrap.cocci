// PatchWeaver callback_livepatch_wrap
// Match functions that need callback based livepatch scaffolding
//
// The first P1 template records Coccinelle intent and keeps the source diff stable
// Execution side materializes kernel_adapter_scaffold.c for hook review
@ callback_candidate @
identifier fn;
@@
fn(...)
{
  ...
}
