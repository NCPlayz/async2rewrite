from collections import Counter
import warnings
import ast


easy_stateful_list = ['add_reaction', 'add_roles', 'ban', 'clear_reactions', 'create_invite', 'create_custom_emoji',
                      'create_role', 'kick', 'remove_reaction', 'remove_roles', 'prune_members', 'unban',
                      'get_message', 'estimate_pruned_members']

easy_deletes_list = ['delete_custom_emoji', 'delete_channel', 'delete_invite', 'delete_message', 'delete_guild']

easy_edits_list = ['edit_channel', 'edit_custom_emoji', 'edit_guild']

removed_methods = ['wait_until_login', 'messages']

stats_counter = Counter()


def find_arg(call: ast.Call, arg_name: str, arg_pos: int=None):
    found_value = None
    for kw in call.keywords:
        if arg_name == kw.arg:
            found_value = kw.value
            break
    else:
        try:
            found_value = call.args[arg_pos]
        except (IndexError, TypeError):
            pass
    return found_value


class DiscordTransformer(ast.NodeTransformer):

    def visit_FormattedValue(self, node):
        self.generic_visit(node)

        return node

    def visit_Module(self, node):
        self.generic_visit(node)

    def visit_keyword(self, node):
        if node.arg == "game" and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute):
            node = self.game_to_activity(node)

        return node

    def visit_Expr(self, node):
        self.generic_visit(node)

        node = self.attr_to_meth(node)

        return node

    def visit_Call(self, node):
        """Modify calls to their appropriate rewrite counterparts."""
        self.generic_visit(node)

        # this all has to do with the stateful model changes
        node = self.to_messageable(node)
        node = self.easy_statefuls(node)
        node = self.stateful_change_nickname(node)
        node = self.stateful_create_channel(node)
        node = self.easy_deletes(node)
        node = self.stateful_edit_message(node)
        node = self.easy_edits(node)
        node = self.stateful_edit_role(node)
        node = self.stateful_edit_channel_perms(node)
        node = self.stateful_leave_server(node)
        node = self.stateful_pin_message(node)
        node = self.stateful_get_bans(node)
        node = self.stateful_pins_from(node)
        node = self.stateful_send_typing(node)
        node = self.stateful_wait_for(node)
        node = self.to_tuple_to_to_rgb(node)
        node = self.channel_history(node)
        node = self.stateful_send_file(node)
        node = self.stateful_delete_channel_perms(node)
        node = self.stateful_delete_role(node)
        node = self.stateful_edit_profile(node)
        node = self.stateful_invites_from(node)
        node = self.stateful_get_reaction_users(node)
        node = self.stateful_move_channel(node)
        node = self.stateful_move_role(node)
        node = self.stateful_move_member(node)
        node = self.stateful_purge_from(node)
        node = self.stateful_replace_roles(node)
        node = self.stateful_server_voice_state(node)
        node = self.stateful_start_private_message(node)

        if isinstance(node.func, ast.Attribute) and node.func.attr == "delete_messages":
            warnings.warn("Cannot convert delete_messages. Must be done manually.")

        if isinstance(node.func, ast.Attribute) and node.func.attr in removed_methods:
            warnings.warn("{} was removed in rewrite. Fix your code accordingly.".format(node.func.attr))

        # Transforms below this comment change the node type.

        node = self.stateful_get_all_emojis(node)

        return node

    def visit_arg(self, node):
        self.generic_visit(node)

        node.arg = node.arg.replace('server', 'guild').replace('Server', 'Guild')
        return node

    def visit_Attribute(self, node):
        self.generic_visit(node)

        node = self.to_edited_at(node)

        self.detect_voice(node)

        if node.attr == "game":
            node.attr = "activity"

        node.attr = node.attr.replace('server', 'guild').replace('Server', 'Guild')
        return node

    def visit_Name(self, node):
        self.generic_visit(node)

        node.id = node.id.replace('server', 'guild').replace('Server', 'Guild')
        return node

    def visit_Await(self, node):
        self.generic_visit(node)

        return node

    def visit_AsyncFunctionDef(self, node):
        self.generic_visit(node)

        node = self.ext_event_changes(node)
        node = self.ensure_ctx_var(node)
        node = self.remove_passcontext(node)
        node = self.event_changes(node)

        node.name = node.name.replace('server', 'guild').replace('Server', 'Guild')

        return node

    def visit_Assign(self, node):
        self.generic_visit(node)

        return node

    def ext_event_changes(self, coro):
        if coro.name == 'on_command' or coro.name == 'on_command_completion':

            coro.args.args = coro.args.args[1:]
            stats_counter['coro_changes'] += 1
            return coro
        elif coro.name == 'on_command_error':

            coro.args.args.reverse()
            stats_counter['coro_changes'] += 1
            return coro

        return coro

    def event_changes(self, coro):
        if coro.name == 'on_voice_state_update':
            coro.args.args.insert(0, ast.arg(arg='member', annotation=None))

        elif coro.name in ['on_guild_emojis_update', 'on_member_ban']:
            coro.args.args.insert(0, ast.arg(arg='guild', annotation=None))

        elif coro.name in ['on_channel_delete', 'on_channel_create', 'on_channel_update']:
            coro.name = coro.name.replace('on_channel', 'on_guild_channel')

        stats_counter['coro_changes'] += 1
        return coro

    def game_to_activity(self, node):
        new_keyword = ast.keyword(arg="activity", value=None)

        activity_wrapper = ast.Call(func=ast.Attribute(value=ast.Name(id="discord", ctx=ast.Load()),
                                                       attr="Activity", ctx=ast.Load()), args=[], keywords=[])

        enum = ast.Attribute(value=ast.Attribute(
            value=ast.Name(id="discord", ctx=ast.Load()),
            attr="ActivityType", ctx=ast.Load()),
            attr=None, ctx=ast.Load())

        game_type = 0
        keywords = list(node.value.keywords)
        for kw in node.value.keywords:
            if kw.arg == "type":
                keywords.remove(kw)
                game_type = kw.value.n

        if game_type == 0:
            node.arg = "activity"
            return node
        elif game_type == 1:
            enum = ast.Attribute(value=ast.Name(id="discord", ctx=ast.Load()), attr="Streaming", ctx=ast.Load())
            new_keyword.value = ast.Call(func=enum, keywords=keywords, args=[])
        else:
            enum.attr = "listening" if game_type == 2 else "watching"
            activity_wrapper.keywords = [ast.keyword(arg="type", value=enum)]
            activity_wrapper.keywords += keywords
            new_keyword.value = activity_wrapper

        return new_keyword

    def detect_voice(self, node):
        if getattr(node, 'attr', None) in ["create_ffmpeg_player", "create_ytdl_player",
                                           "create_stream_player", "play_audio"]:
            warnings.warn("Voice implementation detected. This library does not convert voice.")

        return node

    def ensure_ctx_var(self, coro):

        d_list = []
        for d in coro.decorator_list:
            if isinstance(d, ast.Attribute):
                d_list.append(d.attr)
            elif isinstance(d, ast.Call):
                if isinstance(d.func, ast.Attribute):
                    d_list.append(d.func.attr)
        if 'command' not in d_list:
            return coro

        coro_args = [arg.arg for arg in coro.args.args]

        if not coro_args:
            coro.args.args.append(ast.arg(arg='ctx', annotation=None))
        elif 'self' in coro_args and 'ctx' not in coro_args:
            coro.args.args.insert(1, ast.arg(arg='ctx', annotation=None))
        elif 'self' not in coro_args and 'ctx' not in coro_args:
            coro.args.args.insert(0, ast.arg(arg='ctx', annotation=None))

        stats_counter['coro_changes'] += 1

        return coro

    def to_edited_at(self, attribute):
        if attribute.attr == 'edited_timestamp':
            attribute.attr = 'edited_at'
            stats_counter['attribute_changes'] += 1

        return attribute

    def attr_to_meth(self, expr):
        if isinstance(expr.value, ast.Attribute):
            if expr.value.attr in ['is_ready', 'is_default', 'is_closed']:
                call = ast.Call()
                call.args = []
                call.keywords = []
                call.func = expr.value
                expr.value = call
                stats_counter['expr_changes'] += 1

        return expr

    def remove_passcontext(self, n):
        for d in n.decorator_list:
            if not isinstance(d, ast.Call):
                continue
            for kw in list(d.keywords):  # iterate over a copy of the list to avoid removing while iterating
                if not isinstance(kw.value, ast.NameConstant):
                    continue
                if kw.arg == 'pass_context':  # if the pass_context kwarg is set to True
                    d.keywords.remove(kw)
                    stats_counter['coro_changes'] += 1
        return n

    def stateful_get_all_emojis(self, call):
        if not isinstance(call.func, ast.Attribute):
            return call
        if call.func.attr != 'get_all_emojis':
            return call

        new_expr = ast.Expr()
        ast.copy_location(new_expr, call)
        call.func.attr = 'emojis'
        new_expr.value = call.func
        return new_expr

    def to_messageable(self, call):
        if not isinstance(call.func, ast.Attribute):
            return call
        if call.func.attr == 'say':
            call.func.value = ast.Name(id='ctx', ctx=ast.Load())
            call.func.attr = 'send'
            stats_counter['call_changes'] += 1
        elif call.func.attr == 'send_message':
            destination = find_arg(call, "destination", 0)

            for kw in call.keywords.copy():
                if kw.arg == "destination":
                    call.keywords.remove(kw)

            wrap_attr = ast.Attribute()
            wrap_attr.value = destination
            wrap_attr.attr = 'send'
            wrap_attr.ctx = ast.Load()

            newcall = ast.Call()
            newcall.func = wrap_attr
            newcall.args = call.args[1:]
            newcall.keywords = call.keywords

            newcall = ast.copy_location(newcall, call)
            stats_counter['call_changes'] += 1

            return newcall

        return call

    def stateful_purge_from(self, call):
        if isinstance(call.func, ast.Attribute):
            if call.func.attr == "purge_from":

                call.func.attr = 'purge'
                dest = find_arg(call, "channel", 0)
                call.args = []
                call.func.value = dest

        return call

    def stateful_replace_roles(self, call):
        if isinstance(call.func, ast.Attribute):
            if call.func.attr == "replace_roles":
                call.func.attr = 'edit'
                call.func.value = find_arg(call, 'member', 0)
                roles = call.args[1:]
                call.args = []
                call.keywords = [ast.keyword(arg='roles', value=ast.List(elts=roles, ctx=ast.Store()))]

        return call

    def stateful_server_voice_state(self, call):
        if isinstance(call.func, ast.Attribute):
            if call.func.attr == "guild_voice_state":
                call.func.attr = 'edit'
                call.func.value = find_arg(call, 'member', 0)
                call.args = []

        return call

    def stateful_move_channel(self, call):
        if isinstance(call.func, ast.Attribute):
            if call.func.attr == 'move_channel':
                call.func.attr = 'edit'
                obj = find_arg(call, 'channel', 0)
                pos = find_arg(call, 'position', 1)
                call.func.value = obj
                call.args = []
                call.keywords = [ast.keyword(arg='position', value=pos)]

        return call

    def stateful_start_private_message(self, call):
        if isinstance(call.func, ast.Attribute):
            if call.func.attr == "start_private_message":
                call.func.attr = 'create_dm'
                call.func.value = find_arg(call, 'user', 0)
                call.args = []
                call.keywords = []

        return call

    def stateful_move_role(self, call):
        if isinstance(call.func, ast.Attribute):
            if call.func.attr == 'move_role':
                call.func.attr = 'edit'
                obj = find_arg(call, 'role', 1)
                pos = find_arg(call, 'position', 2)
                call.func.value = obj
                call.args = []
                call.keywords = [ast.keyword(arg='position', value=pos)]

        return call

    def easy_statefuls(self, call):
        if isinstance(call.func, ast.Attribute):
            if call.func.attr in easy_stateful_list:
                message = call.args[0]
                call.func.value = message
                call.args = call.args[1:]
                stats_counter['call_changes'] += 1
        return call

    def easy_deletes(self, call):
        if isinstance(call.func, ast.Attribute):
            if call.func.attr in easy_deletes_list:
                to_delete = call.args[0]
                call.func.value = to_delete
                call.args = call.args[1:]
                call.func.attr = 'delete'
                stats_counter['call_changes'] += 1
        return call

    def easy_edits(self, call):
        if isinstance(call.func, ast.Attribute):
            if call.func.attr in easy_edits_list:
                to_edit = call.args[0]
                call.func.value = to_edit
                call.args = call.args[1:]
                call.func.attr = 'edit'
                stats_counter['call_changes'] += 1
        return call

    def stateful_delete_role(self, call):
        if isinstance(call.func, ast.Attribute):
            if call.func.attr == 'delete_role':
                role = find_arg(call, "role", 1)
                call.func.value = role
                call.func.attr = "delete"
                call.args = []
                call.keywords = []

        return call

    def stateful_send_file(self, call):
        if isinstance(call.func, ast.Attribute):
            if call.func.attr == 'send_file':
                dest = find_arg(call, "destination", 0)
                send_as = find_arg(call, "fp", 1)
                content = None
                filename = None
                for kw in list(call.keywords):
                    if kw.arg in ["destination", "fp"]:
                        call.keywords.remove(kw)
                    elif kw.arg == 'filename':
                        filename = kw
                    elif kw.arg == 'content':
                        content = kw
                if filename is None:
                    filename = ast.keyword(arg='filename', value=send_as)
                call.func.value = dest
                call.func.attr = 'send'
                call.args = []
                if content:
                    call.args.append(content.value)
                call.keywords = []
                file_kw = ast.keyword()
                file_kw.arg = 'file'
                discord_file_call = ast.Call()
                discord_file_call.func = ast.Attribute(value=ast.Name(id='discord', ctx=ast.Load()), attr='File',
                                                       ctx=ast.Load())
                discord_file_call.args = [send_as]
                discord_file_call.keywords = [ast.keyword(arg='filename', value=filename.value)]
                file_kw.value = discord_file_call
                call.keywords.append(file_kw)
                stats_counter['call_changes'] += 1

        return call

    def channel_history(self, call):
        if isinstance(call.func, ast.Attribute):
            if call.func.attr == 'logs_from':
                dest = find_arg(call, "channel", 0)
                call.args.remove(dest)
                if call.args:
                    limit = call.args[0]
                    call.keywords.append(ast.keyword(arg='limit', value=limit))
                    call.args = []
                call.func.value = dest
                call.func.attr = 'history'
                stats_counter['call_changes'] += 1
        return call

    def stateful_change_nickname(self, call):
        if isinstance(call.func, ast.Attribute):
            if call.func.attr == 'change_nickname':
                member = find_arg(call, "member", 0)
                call.func.value = member
                call.func.attr = 'edit'
                nick = find_arg(call, "nickname", 1)
                call.args = []
                call.keywords = [ast.keyword(arg='nick', value=nick)]
                stats_counter['call_changes'] += 1
        return call

    def stateful_pins_from(self, call):
        if isinstance(call.func, ast.Attribute):
            if call.func.attr == 'pins_from':
                dest = find_arg(call, "channel", 0)
                call.func.value = dest
                call.func.attr = 'pins'
                call.args = []
                stats_counter['call_changes'] += 1
        return call

    def stateful_wait_for(self, call):
        if isinstance(call.func, ast.Attribute):
            if call.func.attr in ['wait_for_message', 'wait_for_reaction']:
                event = call.func.attr.split('_')[2]
                event = 'message' if event == 'message' else 'reaction_add'
                call.func.attr = 'wait_for'
                if call.args:
                    timeout = call.args[0]
                    call.args = []
                    call.keywords.append(ast.keyword(arg='timeout', value=timeout))

                call.args.insert(0, ast.Str(s=event))
                for kw in list(call.keywords):
                    if kw.arg != 'check' and kw.arg != 'timeout':
                        call.keywords.remove(kw)
                        warnings.warn('wait_for keyword breaking change detected. Rewrite removes the {} keyword'
                                      ' from wait_for.'.format(kw.arg))
                    elif kw.arg == 'timeout':
                        warnings.warn('wait_for timeout breaking change detected. Timeouts now raise '
                                      'asyncio.TimeoutError instead of returning None.')

                stats_counter['call_changes'] += 1
        return call

    def stateful_edit_role(self, call):
        if isinstance(call.func, ast.Attribute):
            if call.func.attr == 'edit_role':
                to_edit = find_arg(call, "role", 1)
                call.func.value = to_edit
                call.args = call.args[2:]
                call.func.attr = 'edit'
                stats_counter['call_changes'] += 1
        return call

    def stateful_get_reaction_users(self, call):
        if isinstance(call.func, ast.Attribute):
            if call.func.attr == 'get_reaction_users':
                call.func.attr = 'users'
                rxn = find_arg(call, 'reaction', 0)
                call.func.value = rxn
                call.args = call.args[1:]
        return call

    def stateful_invites_from(self, call):
        if isinstance(call.func, ast.Attribute):
            if call.func.attr == 'invites_from':
                call.func.attr = 'invites'
                call.func.value = find_arg(call, 'server', 0)
                call.args = []
                call.keywords = []

        return call

    def to_tuple_to_to_rgb(self, call):
        if isinstance(call.func, ast.Attribute):
            if call.func.attr == 'to_tuple':
                call.func.attr = 'to_rgb'
                stats_counter['call_changes'] += 1

        return call

    def stateful_send_typing(self, call):
        if isinstance(call.func, ast.Attribute):
            if call.func.attr == 'send_typing':
                dest = find_arg(call, "destination", 0)
                call.func.value = dest
                call.args = call.args[1:]
                call.func.attr = 'trigger_typing'
                stats_counter['call_changes'] += 1
        return call

    def stateful_create_channel(self, call):
        if isinstance(call.func, ast.Attribute):
            if call.func.attr == 'create_channel':
                for kw in list(call.keywords):
                    if isinstance(kw.value, ast.Attribute):
                        channel_type = kw.value.attr
                        call.keywords.remove(kw)
                        break
                else:
                    channel_type = 'text'
                call.func.attr = 'create_{}_channel'.format(channel_type)
                guild = find_arg(call, "guild", 0)
                if guild:
                    call.args = call.args[1:]
                call.func.value = guild
                stats_counter['call_changes'] += 1
        return call

    def stateful_edit_message(self, call):
        if isinstance(call.func, ast.Attribute):
            if call.func.attr == 'edit_message':
                call.func.attr = 'edit'
                message = find_arg(call, "message", 0)
                call.func.value = message
                content = find_arg(call, "new_content", 1)
                call.args = call.args[2:]
                if content is not None:
                    call.keywords.append(ast.keyword(arg='content', value=content))
                stats_counter['call_changes'] += 1
        return call

    def stateful_edit_profile(self, call):
        if isinstance(call.func, ast.Attribute):
            if call.func.attr == 'edit_profile':
                call.func.attr = 'user.edit'

        return call

    def stateful_edit_channel_perms(self, call):
        if isinstance(call.func, ast.Attribute):
            if call.func.attr == 'edit_channel_permissions':
                call.func.attr = 'set_permissions'
                channel = find_arg(call, "channel", 0)
                call.func.value = channel
                target = find_arg(call, "target", 1)
                call.args = [target]
                stats_counter['call_changes'] += 1
        return call

    def stateful_delete_channel_perms(self, call):
        if isinstance(call.func, ast.Attribute):
            if call.func.attr == 'delete_channel_permissions':
                call.func.attr = 'set_permissions'
                channel = find_arg(call, "channel", 0)
                call.func.value = channel
                call.args = []
                call.keywords = []
                call.keywords.append(ast.keyword(arg='overwrite', value=ast.NameConstant(None)))
                stats_counter['call_changes'] += 1

        return call

    def stateful_leave_server(self, call):
        if isinstance(call.func, ast.Attribute):
            if call.func.attr == 'leave_guild':
                server = find_arg(call, "server", 0)
                call.func.value = server
                call.func.attr = 'leave'
                call.args = []
                stats_counter['call_changes'] += 1
        return call

    def stateful_move_member(self, call):
        if isinstance(call.func, ast.Attribute):
            if call.func.attr == 'move_member':
                call.func.attr = 'edit'
                member = find_arg(call, 'member', 0)
                channel = find_arg(call, 'channel', 1)
                call.func.value = member
                call.args = []
                call.keywords = [ast.keyword(arg='voice_channel', value=channel)]

        return call

    def stateful_pin_message(self, call):
        if isinstance(call.func, ast.Attribute):
            if call.func.attr == 'pin_message':
                message = find_arg(call, "message", 0)
                call.func.value = message
                call.func.attr = 'pin'
                call.args = []
            elif call.func.attr == 'unpin_message':
                message = find_arg(call, "message", 0)
                call.func.value = message
                call.func.attr = 'unpin'
                call.args = []
                stats_counter['call_changes'] += 1
        return call

    def stateful_get_bans(self, call):
        if isinstance(call.func, ast.Attribute):
            if call.func.attr == 'get_bans':
                guild = find_arg(call, "server", 0)
                call.func.value = guild
                call.func.attr = 'bans'
                call.args = []
                stats_counter['call_changes'] += 1
        return call


def find_stats(ast):
    DiscordTransformer().generic_visit(ast)
    return stats_counter
