"""block8 pipeline

Revision ID: 3d968145ad71
Revises: 
Create Date: 2026-08-16 03:49:04.480874

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import sqlmodel

# revision identifiers, used by Alembic.
revision: str = '3d968145ad71'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Crear tabla pipelinestage
    op.create_table('pipelinestage',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('job_offer_id', sa.Integer(), nullable=False),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(length=60), nullable=False),
        sa.Column('order_index', sa.Integer(), nullable=False),
        sa.Column('kind', sqlmodel.sql.sqltypes.AutoString(length=15), nullable=False),
        sa.ForeignKeyConstraint(['job_offer_id'], ['joboffer.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('job_offer_id', 'order_index', name='uq_job_offer_order_index')
    )

    # 2. Modificar application
    op.add_column('application', sa.Column('current_stage_id', sa.Integer(), nullable=True))
    op.add_column('application', sa.Column('outcome', sqlmodel.sql.sqltypes.AutoString(length=15), nullable=True))
    op.create_foreign_key('fk_app_stage', 'application', 'pipelinestage', ['current_stage_id'], ['id'])

    # 3. Modificar decision
    op.add_column('decision', sa.Column('from_stage_id', sa.Integer(), nullable=True))
    op.add_column('decision', sa.Column('to_stage_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_dec_from_stage', 'decision', 'pipelinestage', ['from_stage_id'], ['id'])
    op.create_foreign_key('fk_dec_to_stage', 'decision', 'pipelinestage', ['to_stage_id'], ['id'])

    # 4. Migración de datos
    connection = op.get_bind()
    offers = connection.execute(sa.text("SELECT id FROM joboffer")).fetchall()
    admin_id = connection.execute(sa.text("SELECT id FROM \"user\" WHERE role='admin' LIMIT 1")).scalar()

    for offer in offers:
        offer_id = offer[0]
        res = connection.execute(sa.text(f"""
            INSERT INTO pipelinestage (job_offer_id, name, order_index, kind) VALUES 
            ({offer_id}, 'Pendiente', 1, 'inicial'),
            ({offer_id}, 'Preselección', 2, 'proceso'),
            ({offer_id}, 'Entrevista 1', 3, 'proceso'),
            ({offer_id}, 'Entrevista final', 4, 'proceso'),
            ({offer_id}, 'Finalista', 5, 'final')
            RETURNING id, name
        """)).fetchall()
        
        stages = {row[1]: row[0] for row in res}
        
        connection.execute(sa.text(f"UPDATE application SET current_stage_id = {stages['Pendiente']} WHERE job_offer_id = {offer_id} AND status = 'pending'"))
        connection.execute(sa.text(f"UPDATE application SET current_stage_id = {stages['Preselección']} WHERE job_offer_id = {offer_id} AND status = 'reviewed'"))
        connection.execute(sa.text(f"UPDATE application SET current_stage_id = {stages['Pendiente']}, outcome = 'descartado' WHERE job_offer_id = {offer_id} AND status = 'rejected'"))
        
        if admin_id:
            apps = connection.execute(sa.text(f"SELECT id, current_stage_id FROM application WHERE job_offer_id = {offer_id}")).fetchall()
            for app in apps:
                if app[1] is not None:
                    connection.execute(sa.text(f"""
                        INSERT INTO decision (application_id, user_id, action, discrepancy_reason, decided_at, to_stage_id)
                        VALUES ({app[0]}, {admin_id}, 'migracion', 'Migrado a pipeline', now(), {app[1]})
                    """))

def downgrade() -> None:
    op.drop_constraint('fk_dec_to_stage', 'decision', type_='foreignkey')
    op.drop_constraint('fk_dec_from_stage', 'decision', type_='foreignkey')
    op.drop_column('decision', 'to_stage_id')
    op.drop_column('decision', 'from_stage_id')
    op.drop_constraint('fk_app_stage', 'application', type_='foreignkey')
    op.drop_column('application', 'outcome')
    op.drop_column('application', 'current_stage_id')
    op.drop_table('pipelinestage')
