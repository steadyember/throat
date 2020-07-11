""" Admin endpoints """
import time
import re
from peewee import fn, JOIN, Value
from pyotp import TOTP
from flask import Blueprint, abort, redirect, url_for, session, render_template, jsonify
from flask_login import login_required, current_user
from flask_babel import _
from .. import misc
from ..forms import TOTPForm, LogOutForm, UseInviteCodeForm, AssignUserBadgeForm, EditModForm, BanDomainForm
from ..models import UserMetadata, User, Sub, SubPost, SubPostComment, SubPostCommentVote, SubPostVote, SiteMetadata
from ..models import UserUploads, SubPostReport, SubPostCommentReport, InviteCode
from ..misc import engine, getReports
from ..badges import badges

bp = Blueprint('admin', __name__)


@bp.route('/admin/auth', methods=['GET', 'POST'])
@login_required
def auth():
    if not current_user.can_admin:
        abort(404)
    form = TOTPForm()
    try:
        user_secret = UserMetadata.get((UserMetadata.uid == current_user.uid) & (UserMetadata.key == 'totp_secret'))
    except UserMetadata.DoesNotExist:
        return engine.get_template('admin/totp.html').render({'authform': form, 'error': _('No TOTP secret found.')})
    if form.validate_on_submit():
        totp = TOTP(user_secret.value)
        if totp.verify(form.totp.data):
            session['apriv'] = time.time()
            return redirect(url_for('admin.index'))
        else:
            return engine.get_template('admin/totp.html').render(
                {'authform': form, 'error': _('Invalid or expired token.')})
    return engine.get_template('admin/totp.html').render({'authform': form, 'error': None})


@bp.route('/logout', methods=['POST'])
@login_required
def logout():
    if not current_user.can_admin:
        abort(404)
    form = LogOutForm()
    if form.validate():
        del session['apriv']
    return redirect(url_for('admin.index'))


@bp.route("/")
@login_required
def index():
    """ WIP: View users. assign badges, etc """
    if not current_user.can_admin:
        abort(404)

    if not current_user.admin:
        return redirect(url_for('admin.auth'))

    users = User.select().count()
    subs = Sub.select().count()
    posts = SubPost.select().count()
    comms = SubPostComment.select().count()
    ups = SubPostVote.select().where(SubPostVote.positive == 1).count()
    downs = SubPostVote.select().where(SubPostVote.positive == 0).count()
    ups += SubPostCommentVote.select().where(SubPostCommentVote.positive == 1).count()
    downs += SubPostCommentVote.select().where(SubPostCommentVote.positive == 0).count()

    invite = UseInviteCodeForm()

    try:
        level = SiteMetadata.get(SiteMetadata.key == 'invite_level')
        maxcodes = SiteMetadata.get(SiteMetadata.key == 'invite_max')
        invite.minlevel.data = level.value
        invite.maxcodes.data = maxcodes.value
    except SiteMetadata.DoesNotExist:
        pass

    try:
        ep = 'True' if SiteMetadata.get(SiteMetadata.key == 'enable_posting').value == '1' else 'False'
    except SiteMetadata.DoesNotExist:
        ep = 'True'

    try:
        er = 'True' if SiteMetadata.get(SiteMetadata.key == 'enable_registration').value == '1' else 'False'
    except SiteMetadata.DoesNotExist:
        er = 'True'

    return render_template('admin/admin.html', subs=subs,
                           posts=posts, ups=ups, downs=downs, users=users,
                           comms=comms, useinvitecode=invite,
                           enable_posting=(ep == 'True'),
                           enable_registration=(er == 'True'))


@bp.route("/users", defaults={'page': 1})
@bp.route("/users/<int:page>")
@login_required
def users(page):
    """ WIP: View users. """
    if not current_user.is_admin():
        abort(404)

    postcount = SubPost.select(SubPost.uid, fn.Count(SubPost.pid).alias('post_count')).group_by(SubPost.uid).alias(
        'post_count')
    commcount = SubPostComment.select(SubPostComment.uid, fn.Count(SubPostComment.cid).alias('comment_count')).group_by(
        SubPostComment.uid).alias('j2')

    users = User.select(User.name, User.status, User.uid, User.joindate, postcount.c.post_count.alias('post_count'),
                        commcount.c.comment_count)
    users = users.join(postcount, JOIN.LEFT_OUTER, on=User.uid == postcount.c.uid)
    users = users.join(commcount, JOIN.LEFT_OUTER, on=User.uid == commcount.c.uid)
    users = users.order_by(User.joindate.desc()).paginate(page, 50).dicts()
    return render_template('admin/users.html', users=users, page=page,
                           admin_route='admin.users')


@bp.route("/userbadges")
@login_required
def userbadges():
    """ WIP: Assign user badges. """
    if not current_user.is_admin():
        abort(404)
    ct = misc.getAdminUserBadges()

    return render_template('admin/userbadges.html', badges=badges.items(),
                           assignuserbadgeform=AssignUserBadgeForm(),
                           ct=len(ct), admin_route='admin.userbadges')


@bp.route("/invitecodes")
@login_required
def invitecodes():
    """
    View and configure Invite Codes
    """
    if not current_user.is_admin():
        abort(404)

    invite_settings = {
        meta.key: meta.value
        for meta in SiteMetadata.select().where(
            SiteMetadata.key in ('useinvitecode', 'invite_level', 'invite_max'))
    }

    invite_codes = InviteCode.select(
        InviteCode.code,
        User.name.alias('referrer_user_name'),
        InviteCode.created,
        InviteCode.expires,
        InviteCode.uses,
        InviteCode.max_uses,
    ).join(User).dicts()

    invite = UseInviteCodeForm()
    return render_template(
        'admin/invitecodes.html',
        useinvitecodeform=invite,
        invite_settings=invite_settings,
        invite_codes=invite_codes,
    )


@bp.route("/admins")
@login_required
def view():
    """ WIP: View admins. """
    if current_user.is_admin():
        admins = UserMetadata.select().where(UserMetadata.key == 'admin')

        postcount = SubPost.select(SubPost.uid, fn.Count(SubPost.pid).alias('post_count')).group_by(SubPost.uid).alias(
            'post_count')
        commcount = SubPostComment.select(SubPostComment.uid,
                                          fn.Count(SubPostComment.cid).alias('comment_count')).group_by(
            SubPostComment.uid).alias('j2')

        users = User.select(User.name, User.status, User.uid, User.joindate, postcount.c.post_count.alias('post_count'),
                            commcount.c.comment_count)
        users = users.join(postcount, JOIN.LEFT_OUTER, on=User.uid == postcount.c.uid)
        users = users.join(commcount, JOIN.LEFT_OUTER, on=User.uid == commcount.c.uid)
        users = users.where(User.uid << [x.uid for x in admins]).order_by(User.joindate.asc()).dicts()

        return render_template('admin/users.html', users=users, admin_route='admin.view')
    else:
        abort(404)


@bp.route("/usersearch/<term>")
@login_required
def users_search(term):
    """ WIP: Search users. """
    if current_user.is_admin():
        term = re.sub(r'[^A-Za-z0-9.\-_]+', '', term)

        postcount = SubPost.select(SubPost.uid, fn.Count(SubPost.pid).alias('post_count')).group_by(SubPost.uid).alias(
            'post_count')
        commcount = SubPostComment.select(SubPostComment.uid,
                                          fn.Count(SubPostComment.cid).alias('comment_count')).group_by(
            SubPostComment.uid).alias('j2')

        users = User.select(User.name, User.status, User.uid, User.joindate, postcount.c.post_count,
                            commcount.c.comment_count)
        users = users.join(postcount, JOIN.LEFT_OUTER, on=User.uid == postcount.c.uid)
        users = users.join(commcount, JOIN.LEFT_OUTER, on=User.uid == commcount.c.uid)
        users = users.where(User.name.contains(term)).order_by(User.joindate.desc()).dicts()

        return render_template('admin/users.html', users=users, term=term,
                               admin_route='admin.users_search')
    else:
        abort(404)


@bp.route("/subs", defaults={'page': 1})
@bp.route("/subs/<int:page>")
@login_required
def subs(page):
    """ WIP: View subs. Assign new owners """
    if current_user.is_admin():
        subs = Sub.select().paginate(page, 50)
        return render_template('admin/subs.html', subs=subs, page=page, admin_route='admin.subs', editmodform=EditModForm())
    else:
        abort(404)


@bp.route("/subsearch/<term>")
@login_required
def subs_search(term):
    """ WIP: Search for a sub. """
    if current_user.is_admin():
        term = re.sub(r'[^A-Za-z0-9.\-_]+', '', term)
        subs = Sub.select().where(Sub.name.contains(term))
        return render_template('admin/subs.html', subs=subs, term=term, admin_route='admin.subs_search',
                               editmodform=EditModForm())
    else:
        abort(404)


@bp.route("/posts/all/", defaults={'page': 1})
@bp.route("/posts/all/<int:page>")
@login_required
def posts(page):
    """ WIP: View posts. """
    if current_user.is_admin():
        posts = misc.getPostList(misc.postListQueryBase(adminDetail=True), 'new', page).paginate(page, 50).dicts()
        return render_template('admin/posts.html', page=page, admin_route='admin.posts', posts=posts)
    else:
        abort(404)


@bp.route("/postvoting/<term>", defaults={'page': 1})
@bp.route("/postvoting/<term>/<int:page>")
@login_required
def post_voting(page, term):
    """ WIP: View post voting habits """
    if current_user.is_admin():
        try:
            user = User.get(fn.Lower(User.name) == term.lower())
            msg = []
            votes = SubPostVote.select(SubPostVote.positive, SubPostVote.pid, User.name, SubPostVote.datetime,
                                       SubPostVote.pid)
            votes = votes.join(SubPost, JOIN.LEFT_OUTER, on=SubPost.pid == SubPostVote.pid)
            votes = votes.switch(SubPost).join(User, JOIN.LEFT_OUTER, on=SubPost.uid == User.uid)
            votes = votes.where(SubPostVote.uid == user.uid).dicts()
        except User.DoesNotExist:
            votes = []
            msg = 'user not found'

        return render_template('admin/postvoting.html', page=page, msg=msg,
                               admin_route='admin.post_voting',
                               votes=votes, term=term)
    else:
        abort(404)


@bp.route("/commentvoting/<term>", defaults={'page': 1})
@bp.route("/commentvoting/<term>/<int:page>")
@login_required
def comment_voting(page, term):
    """ WIP: View comment voting habits """
    if current_user.is_admin():
        try:
            user = User.get(fn.Lower(User.name) == term.lower())
            msg = []
            votes = SubPostCommentVote.select(SubPostCommentVote.positive, SubPostCommentVote.cid, SubPostComment.uid,
                                              User.name, SubPostCommentVote.datetime, SubPost.pid,
                                              Sub.name.alias('sub'))
            votes = votes.join(SubPostComment, JOIN.LEFT_OUTER, on=SubPostComment.cid == SubPostCommentVote.cid).join(
                SubPost).join(Sub)
            votes = votes.switch(SubPostComment).join(User, JOIN.LEFT_OUTER, on=SubPostComment.uid == User.uid)
            votes = votes.where(SubPostCommentVote.uid == user.uid).dicts()
        except User.DoesNotExist:
            votes = []
            msg = 'user not found'

        return render_template('admin/commentvoting.html', page=page, msg=msg,
                               admin_route='admin.comment_voting',
                               votes=votes, term=term)
    else:
        abort(404)


@bp.route("/post/search/<term>")
@login_required
def post_search(term):
    """ WIP: Post search result. """
    if current_user.is_admin():
        term = re.sub(r'[^A-Za-z0-9.\-_]+', '', term)
        try:
            post = SubPost.get(SubPost.pid == term)
        except SubPost.DoesNotExist:
            return abort(404)

        votes = SubPostVote.select(SubPostVote.positive, SubPostVote.datetime, User.name).join(User).where(
            SubPostVote.pid == post.pid).dicts()
        upcount = post.votes.where(SubPostVote.positive == '1').count()
        downcount = post.votes.where(SubPostVote.positive == '0').count()

        pcount = post.uid.posts.count()
        ccount = post.uid.comments.count()
        comms = SubPostComment.select(SubPostComment.score, SubPostComment.content, SubPostComment.cid, User.name).join(
            User).where(SubPostComment.pid == post.pid).dicts()

        return render_template('admin/post.html', sub=post.sid, post=post,
                               votes=votes, ccount=ccount, pcount=pcount,
                               upcount=upcount, downcount=downcount,
                               comms=comms, user=post.uid)
    else:
        abort(404)


@bp.route("/domains", defaults={'page': 1})
@bp.route("/domains/<int:page>")
@login_required
def domains(page):
    """ WIP: View Banned Domains """
    if current_user.is_admin():
        domains = SiteMetadata.select().where(SiteMetadata.key == 'banned_domain')
        return render_template('admin/domains.html', domains=domains,
                               page=page, admin_route='admin.domains',
                               bandomainform=BanDomainForm())
    else:
        abort(404)


@bp.route("/uploads", defaults={'page': 1})
@bp.route("/uploads/<int:page>")
@login_required
def user_uploads(page):
    """ View user uploads """
    uploads = UserUploads.select().order_by(UserUploads.pid.desc()).paginate(page, 30)
    users = User.select(User.name).join(UserMetadata).where(UserMetadata.key == 'canupload')
    return render_template('admin/uploads.html', page=page, uploads=uploads, users=users)


@bp.route("/reports", defaults={'page': 1})
@bp.route("/reports/<int:page>")
@login_required
def reports(page):
    if not current_user.is_admin():
        abort(404)

    reports = getReports('admin', 'all', page)

    return engine.get_template('admin/reports.html').render({'reports': reports, 'page': page})
